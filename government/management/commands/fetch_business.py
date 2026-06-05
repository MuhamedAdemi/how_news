"""
Management command: python manage.py fetch_business

Merr programet per bizneset dhe SME-te nga:
  - Baze e kuruar: kredi MBDP, grante FITR, investime, regjistrim biznesi
  - mbdp.com.mk: Banka e Zhvillimit
  - economy.gov.mk: Ministria e Ekonomise

Perdorim:
    python manage.py fetch_business
    python manage.py fetch_business --dry
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
        "title_mk": "Kredi per bizneset e vogla dhe te mesme — Banka Zhvillimore MBDP",
        "domain": "biznes",
        "item_type": "loan",
        "institution": "Banka për Zhvillim të Ndërmarrjeve (MBDP / Makedonska Banka za Podpora na Razvojot)",
        "source_url": "https://mbdp.com.mk/mk/krediti/",
        "budget": "nga 50,000 deri 3,000,000 denarë me normë interesi 3-5%",
        "eligible_who": (
            "Ndërmarrjet e vogla dhe të mesme (NVM) të regjistruara në RMV. "
            "Startup-et dhe bizneset ekzistuese. "
            "Fermerët dhe kooperativat bujqësore. "
            "Bizneset me plan të qëndrueshëm dhe histori (ose plan biznesi të mirë)."
        ),
        "documents": (
            "Certifikata e regjistrimit të biznesit (Regjistri Qendror)\n"
            "Numri identifikues tatimor (EDB)\n"
            "Pasqyrat financiare (2 vjet të fundit)\n"
            "Plan biznesi (për startup-et)\n"
            "Dokumentet e kolateralit (pronë, makinë, etj.)\n"
            "Kartë identiteti e pronarit/ortakëve\n"
            "Formulari i aplikimit MBDP"
        ),
        "description": (
            "MBDP — Banka për Zhvillim jep kredi me normë të favorshme për bizneset e vogla "
            "dhe të mesme që nuk mund të marrin kredi nga bankat komerciale. "
            "Norma e interesit është 3-5% në vit — shumë më e ulët se bankat private. "
            "Gracija (pa kthim) deri 12 muaj. Afati i kthimit deri 7 vjet. "
            "Apliko online në mbdp.com.mk ose vizito zyrën në Shkup/qytetet kryesore. "
            "Procesi zgjat rreth 30 ditë."
        ),
    },
    {
        "title_mk": "Grant per startup dhe inovacion — Fondi per Inovacione dhe Zhvillim Teknologjik (FITR)",
        "domain": "biznes",
        "item_type": "grant",
        "institution": "Fondi për Inovacione dhe Zhvillim Teknologjik (FITR)",
        "source_url": "https://fitr.mk/granti/",
        "budget": "nga 200,000 deri 15,000,000 denarë (sipas programit)",
        "eligible_who": (
            "Startup-et dhe ndërmarrjet inovative (teknologji, IT, produkte të reja). "
            "Spin-off universitare dhe projekte kërkimore-zhvillimore. "
            "Ndërmarrjet që eksportojnë ose planifikojnë eksport. "
            "Bizneset me potencial rritjeje dhe vende pune të reja."
        ),
        "documents": (
            "Certifikata e regjistrimit (Regjistri Qendror)\n"
            "Plan biznesi dhe plan inovacioni\n"
            "CV e ekipit themelues\n"
            "Prototip ose proof-of-concept (nëse ka)\n"
            "Buxhet i detajuar i projektit\n"
            "Deklaratë se nuk ka borxhe tatimore\n"
            "Formulari i aplikimit FITR"
        ),
        "description": (
            "FITR jep grante të pakthyeshme për bizneset inovative dhe startup-et. "
            "Ka disa programe: Grant i Vogël (200K-1M denarë), Grant i Mesëm (1-5M), "
            "Grant i Madh (5-15M denarë). "
            "Grant-et mbulojnë: pajisje, softuer, zhvillim produkti, marketing eksporti. "
            "Thirrjet hapen 2-3 herë në vit — kontrollo fitr.mk për thirrjet aktive. "
            "Apliko online. Procesi zgjat rreth 60 ditë."
        ),
    },
    {
        "title_mk": "Regjistrim biznesi — Si te hapesh nje biznes ne RMV",
        "domain": "biznes",
        "item_type": "announcement",
        "institution": "Regjistri Qendror i Republikës së Maqedonisë së Veriut",
        "source_url": "https://www.crm.com.mk/",
        "budget": "Tarifa: 1,500-3,000 denarë (varion sipas llojit)",
        "eligible_who": (
            "Çdo person fizik mbi 18 vjeç me kartë identiteti të vlefshme. "
            "Mund të regjistrohet si: Tregtar Individual (TI), "
            "Shoqëri me Përgjegjësi të Kufizuar (SHPK), "
            "Kooperativë, OJQ, ose forma të tjera."
        ),
        "documents": (
            "Kartë identiteti\n"
            "Vendbanimi (vërtetim adrese)\n"
            "Emri i biznesit (3 alternativa)\n"
            "Adresa e selisë së biznesit\n"
            "Aktiviteti kryesor (kodi NKD)\n"
            "Kapitali fillestar (min. 1 denar për SHPK)\n"
            "Tarifa e regjistrimit (paguhet online ose bankë)"
        ),
        "description": (
            "Hapja e biznesit në RMV bëhet online ose fizikisht në Regjistrin Qendror. "
            "Procedura: 1) Zgjidh formën juridike (TI është më e thjeshtë); "
            "2) Zgjidh emrin e biznesit dhe kontrollo nëse është i lirë; "
            "3) Regjistrohu online në e-biznis.com.mk ose vizito Regjistrin Qendror; "
            "4) Prit 1-3 ditë pune; "
            "5) Merr certifikatën dhe EDB-in (numrin tatimor). "
            "Kostoja totale: rreth 1,500-3,000 denarë. "
            "Pas regjistrimit duhet të hapësh llogari bankare dhe të regjistrohesh tek Drejtoria e të Ardhurave Publike (DAP)."
        ),
    },
    {
        "title_mk": "Subvencion per hapjen e bizneseve ne zonat e pazhvilluara",
        "domain": "biznes",
        "item_type": "subsidy",
        "institution": "Ministria e Ekonomisë / Byroja për Zhvillim Rajonal",
        "source_url": "https://economy.gov.mk/",
        "budget": "deri 50% e investimit, max 2,000,000 denarë",
        "eligible_who": (
            "Bizneset e reja dhe ekzistuese në zonat e pazhvilluara (Maqedonia Perëndimore, "
            "Pellazgu i Vardarit etj.). "
            "Investimet që krijojnë të paktën 5 vende pune të reja. "
            "Bizneset me plan investimi të documentuar."
        ),
        "documents": (
            "Certifikata e regjistrimit\n"
            "Plan biznesi dhe plan investimi\n"
            "Vërtetim se biznesi ndodhet ose do ndodhet në zonë të synuar\n"
            "Dokumentet e punëtorëve të rinj (kontrata pune)\n"
            "Oferta ose fatura pro-forma për investimet\n"
            "Formulari i aplikimit"
        ),
        "description": (
            "Qeveria jep subvencione për bizneset që investojnë dhe krijojnë vende pune "
            "në zonat ekonomikisht të pazhvilluara. "
            "Kjo përfshin shumicën e komunave shqiptare: Tetovë, Gostivar, Kërçovë, "
            "Dibër, Struga dhe komunat rreth tyre. "
            "Subvencioni mbulon deri 50% të investimit në pajisje, ndërtesa dhe teknologji. "
            "Aplikimi bëhet pranë Ministrisë së Ekonomisë ose Byrosë për Zhvillim Rajonal."
        ),
    },
    {
        "title_mk": "Program per eksport — Ndihme financiare per bizneset eksportuese",
        "domain": "biznes",
        "item_type": "grant",
        "institution": "Agjencia për Promovimin e Sipërmarrjes dhe Investimeve (APSEI) / Ministria e Ekonomisë",
        "source_url": "https://economy.gov.mk/mk/category/izvoz/",
        "budget": "deri 30% e kostove të marketingut dhe certifikimeve ndërkombëtare",
        "eligible_who": (
            "Bizneset e vogla dhe të mesme që eksportojnë ose planifikojnë të eksportojnë. "
            "Bizneset me produkte ose shërbime të gatshme për treg të huaj. "
            "Minimum 1 vit aktivitet biznesore."
        ),
        "documents": (
            "Certifikata e regjistrimit\n"
            "Vërtetim i eksporteve të mëparshme (nëse ka)\n"
            "Plan eksporti\n"
            "Oferta nga panaire ndërkombëtare ose partnerë të huaj\n"
            "Pasqyrat financiare\n"
            "Formulari i aplikimit APSEI"
        ),
        "description": (
            "Bizneset që eksportojnë ose dëshirojnë të hyjnë në tregje të huaja mund të "
            "marrin mbështetje financiare për: pjesëmarrje në panaire ndërkombëtare, "
            "certifikime (ISO, CE, organik), ueb-faqe dhe materiale marketingu në gjuhë "
            "të huaja, takime me blerës ndërkombëtarë. "
            "Apliko pranë APSEI ose Ministrisë së Ekonomisë. "
            "Thirrjet zakonisht hapen 1-2 herë në vit."
        ),
    },
    {
        "title_mk": "Kredi mikrofinancuese per bizneset shume te vogla dhe individet",
        "domain": "biznes",
        "item_type": "loan",
        "institution": "Institucionet e Mikrofinancës (Horizonti, FullFinance, MakPetrol Finans)",
        "source_url": "https://mbdp.com.mk/mk/mikrofinansiranje/",
        "budget": "nga 10,000 deri 300,000 denarë, normë interesi 8-15%",
        "eligible_who": (
            "Individët dhe bizneset shumë të vogla që nuk kualifikohen për kredi bankare. "
            "Fermerët dhe artizanët. "
            "Personat e papunë që dëshirojnë të fillojnë biznes. "
            "Nuk kërkohet histori kreditore."
        ),
        "documents": (
            "Kartë identiteti\n"
            "Certifikata e regjistrimit (nëse ka biznes të regjistruar)\n"
            "Plan i thjeshtë biznesi ose shpjegim i aktivitetit\n"
            "Garanci (person garantues ose pronë e vogël)\n"
            "Formulari i aplikimit"
        ),
        "description": (
            "Mikrofinanca është kredi e vogël (10K-300K denarë) për njerëzit dhe bizneset "
            "e vogla që nuk mund të marrin kredi nga bankat e mëdha. "
            "Norma interesi është 8-15% — më e lartë se MBDP por pa kushte të rrepta. "
            "Ideal për: bujqit, artizanët, dyqanet e vogla, shërbime familjare. "
            "Institucione kryesore: Horizonti, FullFinance. "
            "Procesi zgjat 5-10 ditë pune. Nuk kërkon histori kreditore të gjatë."
        ),
    },
    {
        "title_mk": "Zona ekonomike industriale — Investime me lehtesira tatimore",
        "domain": "biznes",
        "item_type": "announcement",
        "institution": "Drejtoria për Zona Teknologjike dhe Industriale Zhvillimore (DTIZ)",
        "source_url": "https://dtiz.gov.mk/",
        "budget": "0% tatim fitimi deri 10 vjet + 0% tatim dividenti + 0% TVSH",
        "eligible_who": (
            "Kompanitë prodhuese dhe përpunuese. "
            "Bizneset e IT dhe shërbimeve me vlerë të lartë. "
            "Investime minimale: 200,000-500,000 EUR (varion sipas zonës). "
            "Krijim i vendeve të punës."
        ),
        "documents": (
            "Plan biznesi dhe plan investimi\n"
            "Certifikata e regjistrimit (ose letër qëllimi)\n"
            "Dokumentet financiare të kompanisë mëmë (nëse investim i huaj)\n"
            "Kërkesë me shkrim drejtuar DTIZ\n"
            "Formulari i aplikimit"
        ),
        "description": (
            "Zonat Ekonomike dhe Industriale Zhvillimore (TIDZR/Bunkeri, Bunarçuk etj.) "
            "ofrojnë kushte jashtëzakonisht të favorshme tatimore: "
            "0% tatim fitimi deri 10 vjet, 0% tatim dividenti, 0% TVSH për inputet. "
            "Ka zona në Tetovë, Gostivar, Kërçovë dhe qytete të tjera. "
            "Ideal për fabrika, punëtori, qendra call-center dhe IT. "
            "Apliko pranë DTIZ ose Ministrisë së Ekonomisë."
        ),
    },
]

LIVE_SOURCES = [
    {
        "url": "https://mbdp.com.mk/mk/",
        "institution": "Banka për Zhvillim (MBDP)",
        "domain": "biznes",
        "base": "https://mbdp.com.mk",
    },
    {
        "url": "https://economy.gov.mk/",
        "institution": "Ministria e Ekonomisë",
        "domain": "biznes",
        "base": "https://economy.gov.mk",
    },
]


class Command(BaseCommand):
    help = "Shto programet per bizneset dhe SME-te"

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
                f"\n=== Programet per Bizneset (baze e kuruar) ===\n"
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
                data = self._enrich(ai_client, prog) if ai_client else self._fmt(prog)
                self._create_page(data, url, gov_index)
                total += 1
                self.stdout.write(self.style.SUCCESS(f"  [OK] {self._s(data['title'][:70])}"))

        # ── 2. Live scraping ─────────────────────────────────────────────
        self.stdout.write(self.style.HTTP_INFO("\n=== Live scraping ===\n"))
        for source in LIVE_SOURCES:
            items = self._scrape(source["url"], source.get("base", ""))
            self.stdout.write(f"  {source['url']}: {len(items)} linqe\n")
            for item in items[:5]:
                if GovItemPage.objects.filter(source_url=item["url"]).exists():
                    continue
                if self.dry:
                    self.stdout.write(f"  [DRY] {self._s(item['title'][:65])}")
                    total += 1
                    continue
                detail = self._detail(item["url"])
                data = self._ai_live(ai_client, item, detail, source) if ai_client else None
                if data and data.get("title"):
                    if data.get("item_type") not in [c[0] for c in GovItemType.choices]:
                        data["item_type"] = "announcement"
                    if data.get("domain") not in [c[0] for c in ProgramDomain.choices]:
                        data["domain"] = "biznes"
                    self._create_page(data, item["url"], gov_index)
                    total += 1

        suffix = "do te shtoheshin" if self.dry else "te shtuara"
        style = self.style.WARNING if self.dry else self.style.SUCCESS
        self.stdout.write(style(f"\n[{'DRY' if self.dry else 'DONE'}] {total} programe biznesi {suffix}.\n"))

    # ── AI ────────────────────────────────────────────────────────────────

    def _enrich(self, client, prog):
        prompt = f"""Perkthe per shqiptaret e Maqedonise:
PROGRAMI: {prog['title_mk']}
INSTITUCIONI: {prog['institution']}
BUXHETI: {prog['budget']}
KUSH: {prog['eligible_who']}
PERSHKRIMI: {prog['description']}

JSON: {{"title":"titull shqip max 100 kar","simple_explanation":"<p>120-150 fjale per biznesmenet...</p>"}}"""
        try:
            from groq import Groq
            msg = client.chat.completions.create(
                model=GROQ_MODEL, max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = re.sub(r"```(?:json)?", "", msg.choices[0].message.content.strip()).strip("`").strip()
            raw = re.sub(r",\s*([}\]])", r"\1", raw)
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                d = json.loads(m.group())
                return {
                    "title": d.get("title", prog["title_mk"][:100]),
                    "domain": prog["domain"],
                    "item_type": prog["item_type"],
                    "institution": prog["institution"],
                    "simple_explanation": d.get("simple_explanation", f"<p>{prog['description']}</p>"),
                    "eligible_who": prog["eligible_who"],
                    "documents_required": prog["documents"],
                    "budget": prog["budget"],
                }
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"    [!] AI: {str(exc)[:60]}"))
        return self._fmt(prog)

    def _fmt(self, prog):
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

    def _ai_live(self, client, item, detail, source):
        if not client:
            return None
        prompt = f"""Klasifiko per shqiptaret e RMV:
TITULLI: {item['title']}
PERMBAJTJA: {detail.get('text','')[:600]}
JSON: {{"title":"shqip","domain":"biznes","item_type":"announcement",
"institution":"{source['institution']}","simple_explanation":"<p>...</p>",
"eligible_who":"","documents_required":"","budget":""}}"""
        try:
            from groq import Groq
            msg = client.chat.completions.create(
                model=GROQ_MODEL, max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = re.sub(r"```(?:json)?", "", msg.choices[0].message.content.strip()).strip("`").strip()
            raw = re.sub(r",\s*([}\]])", r"\1", raw)
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                return json.loads(m.group())
        except Exception:
            pass
        return None

    # ── Scraping ──────────────────────────────────────────────────────────

    def _scrape(self, url, base=""):
        try:
            s = requests.Session()
            s.max_redirects = 5
            r = s.get(url, timeout=12, verify=False,
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
                    href = b.rstrip("/") + href
                if href.startswith("http") and href not in seen and href != url:
                    seen.add(href)
                    items.append({"title": text[:200], "url": href})
            return items
        except Exception:
            return []

    def _detail(self, url):
        try:
            s = requests.Session()
            s.max_redirects = 5
            r = s.get(url, timeout=10, verify=False,
                      headers={"User-Agent": "Mozilla/5.0"})
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = soup.get_text(" ", strip=True)
            return {"text": " ".join(text.split())[:2000]}
        except Exception:
            return {"text": ""}

    # ── Krijimi ───────────────────────────────────────────────────────────

    def _create_page(self, data, url, gov_index):
        gov_index = GovIndexPage.objects.live().get(pk=gov_index.pk)
        slug = self._unique_slug(slugify(data["title"])[:80] or "program-biznesi", gov_index)
        page = GovItemPage(
            title=data["title"], slug=slug,
            item_type=data.get("item_type", "announcement"),
            domain=data.get("domain", "biznes"),
            status=GovItemStatus.ACTIVE,
            institution=data.get("institution", ""),
            budget=data.get("budget", ""),
            eligible_who=data.get("eligible_who", ""),
            documents_required=data.get("documents_required", ""),
            original_url=url, source_url=url,
            simple_explanation=data.get("simple_explanation", ""),
        )
        gov_index.add_child(instance=page)
        page.save_revision().publish()

    def _unique_slug(self, base_slug, parent):
        slug, counter = base_slug, 1
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
