"""
Management command: python manage.py fetch_employment

Merr programet e punesimit nga:
  - Baza e kuruar e programeve te njohura (AVRM/MLS)
  - mls.gov.mk kur eshte i aksesueshëm
  - mtsp.gov.mk per njoftimet sociale

Programet e punesimit ne RMV jane te njohura dhe relativisht stabile —
ndryshojne vetem shuma dhe afatet, jo strukturen. Kjo qasje hibride
kombinon baze te kuruar me scraping live.

Perdorim:
    python manage.py fetch_employment          # te gjitha programet
    python manage.py fetch_employment --dry    # shfaq pa ruajtur
    python manage.py fetch_employment --live   # vetem scraping live (pa bazë)
"""
import json
import os
import re
import warnings

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from wagtail.models import Page

from government.models import (
    GovIndexPage,
    GovItemPage,
    GovItemStatus,
    GovItemType,
    ProgramDomain,
)

warnings.filterwarnings("ignore")

GROQ_MODEL = "llama-3.3-70b-versatile"

# ── Baza e kuruar: Programet e njohura te punësimit në RMV ───────────────────
# Burim: AVRM, MLS, programet operative të politikës aktive të punës
# Përditëso këtu kur ndryshojnë shumat/afatet

KNOWN_PROGRAMS = [
    {
        "title_mk": "Самовработување — Субвенција за отворање сопствен бизнис",
        "domain": "punesim",
        "item_type": "grant",
        "institution": "Agjencia e Punësimit e Republikës së Maqedonisë së Veriut (AVRM)",
        "source_url": "https://www.avrm.gov.mk/programi/aktivni-merki/samovrabotuvanje",
        "budget": "deri 230,000 denarë (rreth 3,750 EUR)",
        "eligible_who": (
            "Personat e regjistruar si të papunë pranë AVRM-it. "
            "Duhet të mos kenë pasur biznes të regjistruar në 12 muajt e fundit. "
            "Nuk kërkohet arsim i caktuar."
        ),
        "documents": (
            "Kartë identiteti\n"
            "Vërtetim nga AVRM se je i regjistruar si i papunë\n"
            "Plan biznesi (formulari i AVRM)\n"
            "Certifikatë e kualifikimeve/trajnimeve (nëse ka)\n"
            "Deklaratë se nuk ka biznes aktiv"
        ),
        "description": (
            "Programi i vetëpunësimit u jep personave të papunë subvencion financiar "
            "për të hapur biznesin e tyre të vogël. Subvencioni është deri 230,000 denarë "
            "dhe nuk duhet të kthehet nëse biznesi mbetet aktiv të paktën 2 vjet. "
            "Aplikimi bëhet pranë çdo zyre rajonale të AVRM. Thirrja zakonisht hapet "
            "janar-mars dhe gusht-shtator."
        ),
    },
    {
        "title_mk": "Субвенционирано вработување — Punëdhënës merr subvencion për punësimin e personit të papunë",
        "domain": "punesim",
        "item_type": "subsidy",
        "institution": "Agjencia e Punësimit e RMV (AVRM)",
        "source_url": "https://www.avrm.gov.mk/programi/aktivni-merki/subvencionirano",
        "budget": "deri 12 paga minimale (rreth 240,000 denarë)",
        "eligible_who": (
            "Punëdhënësit (bizneset) që punësojnë persona nga lista e AVRM. "
            "Kandidatët duhet të jenë të papunë dhe të regjistruar pranë AVRM. "
            "Prioritet: persona mbi 50 vjec, gra, persona me aftësi të kufizuara."
        ),
        "documents": (
            "Certifikata e regjistrimit të biznesit (tregtar individual ose shoqëri)\n"
            "Numri identifikues tatimor (EDB)\n"
            "Kontrata e punës me të punësuarin e ri\n"
            "Vërtetim nga AVRM për kandidatin\n"
            "Formulari i aplikimit (merret pranë AVRM)"
        ),
        "description": (
            "Bizneset që punësojnë persona të papunë nga evidenca e AVRM marrin subvencion "
            "mujor për pagën e punëtorit. Subvencioni mbulon 50-100% të pagës minimale "
            "për 6-12 muaj. Ky program është ideal për bizneset e vogla dhe të mesme. "
            "Aplikimi bëhet pranë zyrës rajonale të AVRM ku ndodhet biznesi."
        ),
    },
    {
        "title_mk": "Обука за вработување — Trajnim profesional falas për personat e papunë",
        "domain": "punesim",
        "item_type": "competition",
        "institution": "Agjencia e Punësimit e RMV (AVRM)",
        "source_url": "https://www.avrm.gov.mk/programi/aktivni-merki/obuka",
        "budget": "Falas (trajnime të financuara nga AVRM)",
        "eligible_who": (
            "Personat e regjistruar si të papunë pranë AVRM. "
            "Prioritet për ata pa kualifikim profesional ose me kualifikim të vjetëruar. "
            "Pa limit moshe."
        ),
        "documents": (
            "Kartë identiteti\n"
            "Vërtetim nga AVRM se je i regjistruar si i papunë\n"
            "Diploma ose dëftesa e arsimit (kopje)\n"
            "Formulari i aplikimit për trajnim"
        ),
        "description": (
            "AVRM ofron trajnime profesionale falas në profesione me kërkesë të lartë "
            "në tregun e punës: IT, gjuhë të huaja, kuzhinë, mekanikë, ndërtim, kujdes "
            "shëndetësor dhe shumë të tjera. Trajnimet zgjasin 3-6 muaj. Gjatë trajnimit "
            "merret kompensim financiar i vogël. Pas përfundimit ndihmohet me gjetjen e punës. "
            "Aplikimi bëhet pranë zyrës rajonale të AVRM."
        ),
    },
    {
        "title_mk": "Надоместок за невработеност — Kompensim financiar për personat e papunë",
        "domain": "punesim",
        "item_type": "announcement",
        "institution": "Agjencia e Punësimit e RMV (AVRM)",
        "source_url": "https://www.avrm.gov.mk/prava/nadomestok",
        "budget": "50-80% e pagës neto të fundit, por max 80% e pagës minimale",
        "eligible_who": (
            "Personat që kanë humbur punën JO me faj të tyre (largim nga puna, mbyllje biznesi). "
            "Duhet të kenë punuar të paktën 9 muaj nga 18 muajt e fundit. "
            "Duhet të regjistrohen pranë AVRM brenda 30 ditëve nga humbja e punës."
        ),
        "documents": (
            "Kartë identiteti\n"
            "Librezë pune ose kontratë pune (e ndërprerë)\n"
            "Vendim i punëdhënësit për ndërprerje të kontratës\n"
            "Numër bankar (xhirollogari)\n"
            "Formulari i aplikimit (merret pranë AVRM)"
        ),
        "description": (
            "Nëse ke humbur punën dhe ke punuar të paktën 9 muaj, ke të drejtë të marrësh "
            "kompensim mujor nga AVRM. Shuma është 50-80% e pagës tënde neto të fundit, "
            "por jo më shumë se 80% e pagës minimale (rreth 18,000 denarë). "
            "Kohëzgjatja: 1 deri 12 muaj, në varësi të viteve të punës. "
            "Regjistrohu pranë AVRM brenda 30 ditëve nga humbja e punës."
        ),
    },
    {
        "title_mk": "Програма за млади — Punësim i garantuar për të rinjtë 15-29 vjeç",
        "domain": "punesim",
        "item_type": "grant",
        "institution": "Agjencia e Punësimit e RMV (AVRM) + Ministria e Punës",
        "source_url": "https://www.avrm.gov.mk/programi/mladi",
        "budget": "Pagë e subvencionuar deri 12 muaj",
        "eligible_who": (
            "Të rinjtë 15-29 vjeç të papunë dhe të regjistruar pranë AVRM. "
            "Prioritet për ata pa eksperiencë pune dhe pa kualifikim. "
            "Programi është në kuadër të Garancisë EU për Rini."
        ),
        "documents": (
            "Kartë identiteti (ose leje qëndrimi)\n"
            "Vërtetim nga AVRM\n"
            "Diploma ose dëftesa\n"
            "CV (mund të ndihmohet nga AVRM)"
        ),
        "description": (
            "Programi 'Garancia për Rini' garanton çdo të ri 15-29 vjeç një ofertë: "
            "punë, trajnim, prakticë ose arsimim shtesë brenda 4 muajve nga regjistrimi. "
            "Financohet nga BE dhe qeveria. Bizneset që punësojnë të rinj marrin subvencion "
            "pagë deri 12 muaj. "
            "Regjistrohu pranë zyrës rajonale të AVRM në qytetin tënd."
        ),
    },
    {
        "title_mk": "Вработување на лица со попреченост — Punësim i personave me aftësi të kufizuara",
        "domain": "punesim",
        "item_type": "subsidy",
        "institution": "Agjencia e Punësimit e RMV (AVRM) + Agjencia për Persona me Aftësi të Kufizuara",
        "source_url": "https://www.avrm.gov.mk/programi/poprechenost",
        "budget": "Subvencion i plotë i pagës deri 24 muaj + adaptim i ambientit të punës",
        "eligible_who": (
            "Bizneset që punësojnë persona me aftësi të kufizuara. "
            "Personat duhet të kenë vërtetim zyrtar të aftësisë së kufizuar. "
            "Biznesi merr subvencion pagë dhe mund të marrë financim për adaptimin e hapësirës."
        ),
        "documents": (
            "Vërtetim i aftësisë së kufizuar (nga Komisioni mjekësor)\n"
            "Kartë identiteti\n"
            "Certifikata e regjistrimit të biznesit\n"
            "Kontrata e punës\n"
            "Formulari i aplikimit (AVRM)"
        ),
        "description": (
            "Bizneset që punësojnë persona me aftësi të kufizuara marrin subvencion të plotë "
            "të pagës deri 24 muaj, plus financim për adaptimin e hapësirës së punës. "
            "Kjo është një mundësi e mirë për bizneset dhe ndihmon personat më vulnerabël "
            "të integrohen në tregun e punës. "
            "Aplikimi bëhet pranë AVRM ose Agjencisë për Persona me Aftësi të Kufizuara."
        ),
    },
]

LIVE_SOURCES = [
    {
        "url": "https://mls.gov.mk/mk/vrabotuvanje/aktivni-merki/",
        "institution": "Ministria e Punës dhe Politikës Sociale (MLS)",
        "domain": ProgramDomain.EMPLOYMENT,
    },
    {
        "url": "https://mls.gov.mk/mk/odnosi-so-javnost/soopstenija/",
        "institution": "Ministria e Punës dhe Politikës Sociale (MLS)",
        "domain": ProgramDomain.EMPLOYMENT,
    },
]


class Command(BaseCommand):
    help = "Shto programet e punësimit (bazë e kuruar + live scraping)"

    def add_arguments(self, parser):
        parser.add_argument("--dry", action="store_true")
        parser.add_argument("--live", action="store_true", help="Vetem scraping live")
        parser.add_argument("--no-ai", action="store_true")

    def handle(self, *args, **options):
        self.dry = options["dry"]
        self.use_ai = not options["no_ai"] and bool(os.environ.get("GROQ_API_KEY"))

        gov_index = GovIndexPage.objects.live().first()
        if not gov_index:
            self.stderr.write(self.style.ERROR("Nuk u gjet GovIndexPage."))
            return

        ai_client = self._init_ai() if self.use_ai else None
        total = 0

        # ── 1. Baza e kuruar ─────────────────────────────────────────────
        if not options["live"]:
            self.stdout.write(self.style.HTTP_INFO(
                f"\n=== Programet e njohura te punesimit (bazë e kuruar) ===\n"
                f"    {len(KNOWN_PROGRAMS)} programe | AI: {'aktiv' if ai_client else 'jo'}\n"
            ))

            for prog in KNOWN_PROGRAMS:
                url = prog["source_url"]
                if GovItemPage.objects.filter(source_url=url).exists():
                    self.stdout.write(f"  [skip] {prog['title_mk'][:60].encode('ascii','replace').decode()}")
                    continue

                if self.dry:
                    self.stdout.write(
                        f"  [DRY]  {prog['domain']} | {prog['item_type']}\n"
                        f"         {prog['title_mk'][:70].encode('ascii','replace').decode()}"
                    )
                    total += 1
                    continue

                data = self._enrich_with_ai(ai_client, prog) if ai_client else self._format_program(prog)
                self._create_page(data, url, gov_index)
                total += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  [OK] {data['title'][:70].encode('ascii','replace').decode()}"
                ))

        # ── 2. Live scraping ─────────────────────────────────────────────
        self.stdout.write(self.style.HTTP_INFO("\n=== Live scraping MLS ===\n"))
        for source in LIVE_SOURCES:
            items = self._scrape_live(source["url"])
            self.stdout.write(f"  {source['url']}: {len(items)} linqe\n")
            for item in items[:5]:
                if GovItemPage.objects.filter(source_url=item["url"]).exists():
                    continue
                if self.dry:
                    self.stdout.write(f"  [DRY] {item['title'][:70].encode('ascii','replace').decode()}")
                    total += 1
                    continue
                detail = self._fetch_detail(item["url"])
                data = (
                    self._ai_process_live(ai_client, item, detail, source)
                    if ai_client
                    else {
                        "title": item["title"][:200],
                        "domain": source["domain"],
                        "item_type": "announcement",
                        "institution": source["institution"],
                        "simple_explanation": f"<p>{detail.get('text','')[:400]}</p>",
                        "eligible_who": "",
                        "documents_required": "",
                        "budget": "",
                    }
                )
                if data and data.get("title"):
                    valid_types = [c[0] for c in GovItemType.choices]
                    if data.get("item_type") not in valid_types:
                        data["item_type"] = "announcement"
                    valid_domains = [c[0] for c in ProgramDomain.choices]
                    if data.get("domain") not in valid_domains:
                        data["domain"] = "punesim"
                    self._create_page(data, item["url"], gov_index)
                    total += 1

        if not self.dry:
            self.stdout.write(self.style.SUCCESS(f"\n[DONE] {total} programe punesimi te shtuara.\n"))
        else:
            self.stdout.write(self.style.WARNING(f"\n[DRY] {total} programe do te shtoheshin.\n"))

    # ── AI Enrichment ─────────────────────────────────────────────────────

    def _enrich_with_ai(self, client, prog):
        """Perdor AI per te gjeneruar shpjegim me te mire ne Shqip."""
        prompt = f"""Perkthe dhe formuloje kete program punesimi per shqiptaret e Maqedonise se Veriut.

PROGRAMI: {prog['title_mk']}
INSTITUCIONI: {prog['institution']}
BUXHETI: {prog['budget']}
KUSH KA TE DREJTE: {prog['eligible_who']}
DOKUMENTET: {prog['documents']}
PERSHKRIMI: {prog['description']}

Detyrë: Shkruaj titull te qarte ne Shqip (max 100 karaktere) dhe shpjegim 120-160 fjale te
thjeshte per qytetaret. Mos perdor fjale juridike — si te flasesh me nje mik.

Pergjigju VETEM me JSON:
{{
  "title": "titulli shqip",
  "simple_explanation": "<p>shpjegimi...</p>"
}}"""

        try:
            from groq import Groq
            msg = client.chat.completions.create(
                model=GROQ_MODEL, max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.choices[0].message.content.strip()
            raw = re.sub(r"```(?:json)?", "", raw).strip("`").strip()
            raw = re.sub(r",\s*([}\]])", r"\1", raw)
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                ai_data = json.loads(m.group())
                return {
                    "title": ai_data.get("title", prog["title_mk"][:100]),
                    "domain": prog["domain"],
                    "item_type": prog["item_type"],
                    "institution": prog["institution"],
                    "simple_explanation": ai_data.get("simple_explanation", f"<p>{prog['description']}</p>"),
                    "eligible_who": prog["eligible_who"],
                    "documents_required": prog["documents"],
                    "budget": prog["budget"],
                }
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"    [!] AI: {str(exc)[:60]}"))

        return self._format_program(prog)

    def _format_program(self, prog):
        return {
            "title": prog["title_mk"][:100],
            "domain": prog["domain"],
            "item_type": prog["item_type"],
            "institution": prog["institution"],
            "simple_explanation": f"<p>{prog['description']}</p>",
            "eligible_who": prog["eligible_who"],
            "documents_required": prog["documents"],
            "budget": prog["budget"],
        }

    # ── Live scraping ─────────────────────────────────────────────────────

    def _scrape_live(self, url):
        try:
            r = requests.get(url, timeout=12, verify=False,
                             headers={"User-Agent": "Mozilla/5.0"})
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
            items = []
            seen = set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)
                if len(text) < 20:
                    continue
                if href.startswith("/"):
                    href = "https://mls.gov.mk" + href
                if href.startswith("http") and href not in seen and href != url:
                    seen.add(href)
                    items.append({"title": text[:200], "url": href})
            return items
        except Exception:
            return []

    def _fetch_detail(self, url):
        try:
            r = requests.get(url, timeout=10, verify=False,
                             headers={"User-Agent": "Mozilla/5.0"})
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = soup.get_text(" ", strip=True)
            return {"text": " ".join(text.split())[:2000]}
        except Exception:
            return {"text": ""}

    def _ai_process_live(self, client, item, detail, source):
        prompt = f"""Klasifiko dhe perkthe kete njoftim punësimi per shqiptaret e RMV:
TITULLI: {item['title']}
PERMBAJTJA: {detail.get('text','')[:800]}

JSON: {{"title":"shqip","domain":"punesim","item_type":"announcement",
"institution":"{source['institution']}","simple_explanation":"<p>...</p>",
"eligible_who":"","documents_required":"","budget":""}}"""
        try:
            from groq import Groq
            msg = client.chat.completions.create(
                model=GROQ_MODEL, max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.choices[0].message.content.strip()
            raw = re.sub(r"```(?:json)?", "", raw).strip("`").strip()
            raw = re.sub(r",\s*([}\]])", r"\1", raw)
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                return json.loads(m.group())
        except Exception:
            pass
        return None

    # ── Krijimi i faqes ───────────────────────────────────────────────────

    def _create_page(self, data, url, gov_index):
        gov_index = GovIndexPage.objects.live().get(pk=gov_index.pk)
        slug = self._unique_slug(
            slugify(data["title"])[:80] or "program-punesimi", gov_index
        )
        page = GovItemPage(
            title=data["title"],
            slug=slug,
            item_type=data.get("item_type", "announcement"),
            domain=data.get("domain", "punesim"),
            status=GovItemStatus.ACTIVE,
            institution=data.get("institution", ""),
            budget=data.get("budget", ""),
            eligible_who=data.get("eligible_who", ""),
            documents_required=data.get("documents_required", ""),
            original_url=url,
            source_url=url,
            simple_explanation=data.get("simple_explanation", ""),
        )
        gov_index.add_child(instance=page)
        rev = page.save_revision()
        rev.publish()

    def _unique_slug(self, base_slug, parent):
        slug = base_slug
        counter = 1
        while Page.objects.filter(slug=slug, path__startswith=parent.path).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug

    def _init_ai(self):
        try:
            from groq import Groq
            key = os.environ.get("GROQ_API_KEY", "")
            return Groq(api_key=key) if key else None
        except ImportError:
            return None
