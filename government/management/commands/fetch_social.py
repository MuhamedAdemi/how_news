"""
Management command: python manage.py fetch_social

Merr programet sociale nga:
  - Bazë e kuruar: ndihma sociale, shtesa familjare, pension, invaliditet
  - fzo.org.mk: sigurimi shëndetësor
  - mtsp.gov.mk: njoftime sociale

Perdorim:
    python manage.py fetch_social
    python manage.py fetch_social --dry
    python manage.py fetch_social --live   # vetem scraping live
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

KNOWN_PROGRAMS = [
    {
        "title_mk": "Ndihma sociale — E drejta dhe procedura e aplikimit",
        "domain": "social",
        "item_type": "announcement",
        "institution": "Qendra për Punë Sociale (komunale) + Ministria e Punës dhe Politikës Sociale",
        "source_url": "https://mtsp.gov.mk/socijalna-zastita-socijalna-pomoc.nspx",
        "budget": "varion sipas gjendjes familjare — mesatarisht 5,000-9,000 denarë/muaj",
        "eligible_who": (
            "Familjet dhe individët pa të ardhura ose me të ardhura shumë të ulëta. "
            "Kushtet: të ardhurat nën pragun minimal, pa pronë të mjaftueshme, "
            "pa anëtar pune-aftë të papunësuar vullnetarisht. "
            "Personat e vetmuar, të moshuar, me aftësi të kufizuara kanë prioritet."
        ),
        "documents": (
            "Kartë identiteti (të gjithë anëtarët mbi 18 vjeç)\n"
            "Certifikata lindjeje (për fëmijët)\n"
            "Certifikatë e gjendjes civile (familja)\n"
            "Vërtetim i të ardhurave (rrogë, pension, qira — ose deklaratë se nuk ka)\n"
            "Vërtetim pronësie (tapi) ose deklaratë se nuk ka pronë\n"
            "Vërtetim nga AVRM (nëse ka anëtar pune-aftë)\n"
            "Formulari i aplikimit (merret në Qendrën për Punë Sociale)"
        ),
        "description": (
            "Nëse familja ose individi ka të ardhura shumë të ulëta ose nuk ka fare, "
            "ka të drejtë për ndihmë sociale mujore nga shteti. "
            "Shuma varet nga numri i anëtarëve dhe gjendja — zakonisht 5,000-9,000 denarë/muaj. "
            "Aplikimi bëhet pranë Qendrës për Punë Sociale në komunën tënde. "
            "Pas aplikimit, punonjësi social vjen për verifikim brenda 30 ditëve. "
            "Ndihma ripërtërihet çdo 6 muaj nëse gjendja vazhdon."
        ),
    },
    {
        "title_mk": "Shtesa familjare (детски додаток) — Ndihmë financiare për fëmijë",
        "domain": "social",
        "item_type": "subsidy",
        "institution": "Ministria e Punës dhe Politikës Sociale / Qendra për Punë Sociale",
        "source_url": "https://mtsp.gov.mk/detski-dodatak.nspx",
        "budget": "rreth 1,800-2,500 denarë për fëmijë/muaj",
        "eligible_who": (
            "Prindërit me fëmijë 0-18 vjeç (deri 26 nëse studion). "
            "Kushti kryesor: të ardhurat mujore nën kufirin e vendosur nga qeveria. "
            "Fëmijët me aftësi të kufizuara marrin shumë më të lartë."
        ),
        "documents": (
            "Kartë identiteti e prindërve\n"
            "Certifikata lindjeje e fëmijës\n"
            "Vërtetim i regjistrimit në shkollë (për fëmijë mbi 6 vjeç)\n"
            "Vërtetim i të ardhurave familjare (rrogë, pension)\n"
            "Numër bankar (xhirollogari)\n"
            "Formulari i aplikimit (Qendra për Punë Sociale)"
        ),
        "description": (
            "Çdo familje me fëmijë dhe me të ardhura nën kufirin e vendosur ka të drejtë "
            "të marrë shtesë familjare mujore për secilin fëmijë. "
            "Shuma është rreth 1,800-2,500 denarë/fëmijë/muaj. "
            "Për fëmijët me aftësi të kufizuara shuma është shumëfishe. "
            "Apliko pranë Qendrës për Punë Sociale ose online në e-uslugi.gov.mk. "
            "Ndihma transferohet direkt në llogarinë bankare."
        ),
    },
    {
        "title_mk": "Pension i pleqërisë — Kushtet dhe procedura",
        "domain": "social",
        "item_type": "announcement",
        "institution": "Fondi i Pensionit dhe Sigurimit të Invaliditetit (PIOM)",
        "source_url": "https://piom.gov.mk/starosna-penzija",
        "budget": "pension mesatar rreth 18,000-22,000 denarë/muaj (varion nga kontributet)",
        "eligible_who": (
            "Burrat: 64 vjeç me 15 vjet kontribute (ose 40 vjet kontribute pa limit moshe). "
            "Gratë: 62 vjeç me 15 vjet kontribute (deri 2031 gradualisht 64). "
            "Kontributet duhet të jenë paguar tek PIOM (punëdhënësi i paguan automatikisht)."
        ),
        "documents": (
            "Kartë identiteti\n"
            "Librezë pune (ose M4 formular nga çdo punëdhënës)\n"
            "Certifikata e arsimit (diplomë/dëftesë)\n"
            "Certifikatë lindjeje\n"
            "Certifikatë martese (nëse ka)\n"
            "Numër bankar (xhirollogari)\n"
            "Formulari i aplikimit për pension (merret tek PIOM)"
        ),
        "description": (
            "Kur të plotësosh kushtet e moshës dhe të kontributeve, ke të drejtë për pension. "
            "Shuma e pensionit varet nga paga mesatare dhe vitet e punës — zakonisht 40-60% e pagës. "
            "Apliko pranë zyrës së PIOM-it në qytetin tënd ose online. "
            "Procesi zgjat rreth 2-3 muaj. "
            "Pensioni filloi të paguhet nga muaji pas aprovimit. "
            "PIOM ka zyra në Tetovë, Gostivar, Kërçovë dhe qytetet kryesore."
        ),
    },
    {
        "title_mk": "Pension i invaliditetit — Nëse nuk mund të punosh për arsye shëndetësore",
        "domain": "social",
        "item_type": "announcement",
        "institution": "Fondi i Pensionit dhe Sigurimit të Invaliditetit (PIOM)",
        "source_url": "https://piom.gov.mk/invalidska-penzija",
        "budget": "varion — zakonisht 50-70% e pagës mesatare",
        "eligible_who": (
            "Personat që kanë humbur aftësinë për punë për arsye shëndetësore "
            "dhe kanë paguar kontribute (koha minimale varion me moshën). "
            "Komisioni mjekësor i PIOM vlerëson shkallën e invaliditetit."
        ),
        "documents": (
            "Kartë identiteti\n"
            "Dokumentacion mjekësor (diagnozë, vërtetim spitali, diagnoza e mjekut familjar)\n"
            "Librezë pune ose M4 formular\n"
            "Certifikata e arsimit\n"
            "Numër bankar\n"
            "Formulari i aplikimit PIOM"
        ),
        "description": (
            "Nëse nuk mund të punosh më për arsye shëndetësore, ke të drejtë për pension invaliditeti. "
            "Hapat: 1) Mjeku familjar jep referim; 2) Komisioni mjekësor i PIOM vlerëson; "
            "3) Nëse aprovohet, apliko për pension. "
            "Kjo e drejtë nuk kërkon moshë minimale — varet nga vitet e punës dhe diagnoza. "
            "Kontakto PIOM-in në qytetin tënd ose mjekun familjar për ta filluar procesin."
        ),
    },
    {
        "title_mk": "Leja e lindjes dhe shtesa e maternitetit",
        "domain": "social",
        "item_type": "subsidy",
        "institution": "Ministria e Punës dhe Politikës Sociale / Punëdhënësi",
        "source_url": "https://mtsp.gov.mk/porodilno-otsustvo.nspx",
        "budget": "100% e pagës neto deri 9 muaj; pas 9 muajsh pension minimal deri 2 vjet",
        "eligible_who": (
            "Nënat e punësuara dhe kontribuuese. "
            "Nënat e papunësuara marrin shtesë minimale. "
            "Baballarët mund të marrin lejen nëse nëna heq dorë."
        ),
        "documents": (
            "Certifikatë e lindjes së fëmijës\n"
            "Kartë identiteti\n"
            "Librezë pune ose kontratë pune\n"
            "Vërtetim nga mjeku-gjinekologu\n"
            "Numër bankar\n"
            "Kërkesë me shkrim drejtuar punëdhënësit"
        ),
        "description": (
            "Nëna e punësuar ka të drejtë për leje lindjeje me pagë të plotë deri 9 muaj. "
            "Pas 9 muajve, mund të vazhdojë lejen edhe 15 muaj të tjera me pagë minimale. "
            "Gjatë lejes punëdhënësi nuk mund ta largojë nga puna. "
            "Nëna e papunësuar merr shtesë të vogël nga MTSP. "
            "Procesi: Mjeku lëshon vërtetim → Punëdhënësi njoftohet → MTSP mbulonpagesën."
        ),
    },
    {
        "title_mk": "Sigurimi shëndetësor — E drejta dhe procedura e regjistrimit",
        "domain": "shendet",
        "item_type": "announcement",
        "institution": "Fondi i Sigurimit Shëndetësor (FZO / FZOSMM)",
        "source_url": "https://fzo.org.mk/",
        "budget": "shërbime mjekësore falas ose me bashkëpagesë të ulët",
        "eligible_who": (
            "Të gjithë personat e punësuar (kontributi paguhet automatikisht nga rroga). "
            "Personat e papunë mund të regjistrohen nëpërmjet Qendrës për Punë Sociale. "
            "Fëmijët deri 18 vjeç janë automatikisht të siguruar."
        ),
        "documents": (
            "Kartë identiteti\n"
            "Vërtetim nga punëdhënësi (nëse je i punësuar)\n"
            "Vërtetim nga AVRM (nëse je i papunë)\n"
            "Certifikata lindjeje (për fëmijët)\n"
            "Formulari i aplikimit (FZO ose online)"
        ),
        "description": (
            "Çdo banor i RMV duhet të ketë sigurimin shëndetësor aktiv. "
            "Nëse je i punësuar, kontributi paguhet automatikisht nga paga. "
            "Nëse je i papunë, regjistrohu pranë FZO-s ose Qendrës për Punë Sociale. "
            "Me kartën e shëndetit (kartica zdravstvena) ke qasje në mjekun familjar, "
            "specializimin, spitalin dhe ilaçet me çmim të reduktuar. "
            "FZO ka zyra në të gjithë qytetet kryesore të RMV."
        ),
    },
    {
        "title_mk": "Shtesa për personat me aftësi të kufizuara",
        "domain": "social",
        "item_type": "subsidy",
        "institution": "Ministria e Punës dhe Politikës Sociale + Instituti i Shëndetit Publik",
        "source_url": "https://mtsp.gov.mk/invalidnost.nspx",
        "budget": "5,000-15,000 denarë/muaj sipas shkallës së aftësisë së kufizuar",
        "eligible_who": (
            "Personat me aftësi të kufizuara të vlerësuara nga komisioni mjekësor. "
            "Fëmijët me aftësi të kufizuara marrin shtesë shtesë nga familja. "
            "Nuk kërkohet moshë minimale."
        ),
        "documents": (
            "Kartë identiteti\n"
            "Vërtetim i aftësisë së kufizuar nga Komisioni mjekësor shtetëror\n"
            "Certifikata lindjeje (për fëmijët)\n"
            "Dokumentacion mjekësor (diagnoza, hospitalizime)\n"
            "Numër bankar\n"
            "Formulari i aplikimit (Qendra për Punë Sociale)"
        ),
        "description": (
            "Personat me aftësi të kufizuara kanë të drejtë për shtesë mujore financiare, "
            "kujdes shtëpiak, transport falas dhe shërbime rehabilitimi. "
            "Hapat: 1) Mjeku familjar referon tek komisioni; 2) Komisioni mjekësor vlerëson; "
            "3) Marr vërtetim; 4) Apliko pranë Qendrës për Punë Sociale. "
            "Shuma varion nga 5,000 deri 15,000+ denarë sipas shkallës. "
            "Familjet që kujdesen për persona me aftësi të rënda marrin kompensim shtesë."
        ),
    },
]

LIVE_SOURCES = [
    {
        "url": "https://fzo.org.mk/",
        "institution": "Fondi i Sigurimit Shëndetësor (FZO)",
        "domain": "shendet",
    },
    {
        "url": "https://mtsp.gov.mk/",
        "institution": "Ministria e Punës dhe Politikës Sociale",
        "domain": "social",
    },
]


class Command(BaseCommand):
    help = "Shto programet sociale dhe shendetesore"

    def add_arguments(self, parser):
        parser.add_argument("--dry", action="store_true")
        parser.add_argument("--live", action="store_true")
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
                f"\n=== Programet Sociale & Shendetesore (baze e kuruar) ===\n"
                f"    {len(KNOWN_PROGRAMS)} programe | AI: {'aktiv' if ai_client else 'jo'}\n"
            ))

            for prog in KNOWN_PROGRAMS:
                url = prog["source_url"]
                if GovItemPage.objects.filter(source_url=url).exists():
                    self.stdout.write(f"  [skip] {self._s(prog['title_mk'][:65])}")
                    continue

                if self.dry:
                    self.stdout.write(
                        f"  [DRY]  {prog['domain']} | {prog['item_type']}\n"
                        f"         {self._s(prog['title_mk'][:70])}"
                    )
                    total += 1
                    continue

                data = self._enrich_with_ai(ai_client, prog) if ai_client else self._format_program(prog)
                self._create_page(data, url, gov_index)
                total += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  [OK] {self._s(data['title'][:70])}"
                ))

        # ── 2. Live scraping ─────────────────────────────────────────────
        self.stdout.write(self.style.HTTP_INFO("\n=== Live scraping ===\n"))
        for source in LIVE_SOURCES:
            items = self._scrape_live(source["url"], source.get("base", ""))
            self.stdout.write(f"  {source['url']}: {len(items)} linqe\n")
            for item in items[:5]:
                if GovItemPage.objects.filter(source_url=item["url"]).exists():
                    continue
                if self.dry:
                    self.stdout.write(f"  [DRY] {self._s(item['title'][:70])}")
                    total += 1
                    continue
                detail = self._fetch_detail(item["url"])
                data = self._ai_process_live(ai_client, item, detail, source) if ai_client else None
                if data and data.get("title"):
                    valid_types = [c[0] for c in GovItemType.choices]
                    if data.get("item_type") not in valid_types:
                        data["item_type"] = "announcement"
                    valid_domains = [c[0] for c in ProgramDomain.choices]
                    if data.get("domain") not in valid_domains:
                        data["domain"] = source["domain"]
                    self._create_page(data, item["url"], gov_index)
                    total += 1

        if not self.dry:
            self.stdout.write(self.style.SUCCESS(f"\n[DONE] {total} programe sociale te shtuara.\n"))
        else:
            self.stdout.write(self.style.WARNING(f"\n[DRY] {total} programe do te shtoheshin.\n"))

    # ── AI ────────────────────────────────────────────────────────────────

    def _enrich_with_ai(self, client, prog):
        prompt = f"""Perkthe dhe formuloje per shqiptaret e Maqedonise se Veriut:

PROGRAMI: {prog['title_mk']}
INSTITUCIONI: {prog['institution']}
BUXHETI: {prog['budget']}
KUSH KA TE DREJTE: {prog['eligible_who']}
PERSHKRIMI: {prog['description']}

Shkruaj titull te qarte shqip (max 100 kar) dhe shpjegim 120-150 fjale per qytetaret.
JSON vetem: {{"title": "...", "simple_explanation": "<p>...</p>"}}"""

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

    def _ai_process_live(self, client, item, detail, source):
        prompt = f"""Klasifiko per shqiptaret e RMV:
TITULLI: {item['title']}
PERMBAJTJA: {detail.get('text','')[:600]}
JSON: {{"title":"shqip","domain":"social","item_type":"announcement",
"institution":"{source['institution']}","simple_explanation":"<p>...</p>",
"eligible_who":"","documents_required":"","budget":""}}"""
        try:
            from groq import Groq
            msg = client.chat.completions.create(
                model=GROQ_MODEL, max_tokens=500,
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

    # ── Scraping ──────────────────────────────────────────────────────────

    def _scrape_live(self, url, base=""):
        try:
            r = requests.get(url, timeout=12, verify=False,
                             headers={"User-Agent": "Mozilla/5.0"})
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
            items, seen = [], set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)
                if len(text) < 20:
                    continue
                if href.startswith("/"):
                    b = base or url.rstrip("/")
                    href = b.split("/")[0] + "//" + b.split("/")[2] + href
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

    def _create_page(self, data, url, gov_index):
        gov_index = GovIndexPage.objects.live().get(pk=gov_index.pk)
        slug = self._unique_slug(
            slugify(data["title"])[:80] or "program-social", gov_index
        )
        page = GovItemPage(
            title=data["title"],
            slug=slug,
            item_type=data.get("item_type", "announcement"),
            domain=data.get("domain", "social"),
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

    def _s(self, text):
        return str(text).encode("ascii", errors="replace").decode("ascii")
