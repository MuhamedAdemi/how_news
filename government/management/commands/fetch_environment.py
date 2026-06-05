"""
Management command: python manage.py fetch_environment

Merr programet per mjedis dhe energji nga:
  - Baze e kuruar: grante mjedisore, energji e rinovueshme, pylltari
  - moepp.gov.mk: Ministria e Mjedisit dhe Planifikimit Hapësinor
"""
import json, os, re, warnings
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from wagtail.models import Page
from government.models import GovIndexPage, GovItemPage, GovItemStatus, GovItemType, ProgramDomain

warnings.filterwarnings("ignore")
GROQ_MODEL = "llama-3.3-70b-versatile"

KNOWN_PROGRAMS = [
    {
        "title_mk": "Subvencion per instalimin e paneleve diellore (energji fotovoltaike)",
        "domain": "ambient",
        "item_type": "subsidy",
        "institution": "Ministria e Ekonomisë / Rregullatori i Energjisë (ERC)",
        "source_url": "https://economy.gov.mk/mk/obnovlivi-izvori/",
        "budget": "deri 25% e kostos së instalimit, max 150,000 denarë për familje",
        "eligible_who": (
            "Familjet dhe bizneset që instalojnë panele diellore. "
            "Pronarët e shtëpive individuale dhe ndërtesave. "
            "Fermerët dhe kooperativat bujqësore. "
            "Nuk kërkohet minimum — edhe instalime të vogla (3-5 kW) kualifikohen."
        ),
        "documents": (
            "Kartë identiteti\n"
            "Dokumentet e pronësisë (tapi ose kontratë qiraje)\n"
            "Fatura e energjisë elektrike (6 muajt e fundit)\n"
            "Oferta nga instaluesi i certifikuar\n"
            "Leja ndërtimore (nëse kërkohet)\n"
            "Formulari i aplikimit (ERC ose Ministria e Ekonomisë)"
        ),
        "description": (
            "Shteti subvencionon instalimin e paneleve diellore për familjet dhe bizneset. "
            "Subvencioni mbulon deri 25% të kostos totale. "
            "Panelet diellore ulin faturën e rrymës me 60-80% dhe teprica shitet "
            "tek EVN/ESM me çmim fiks (net-metering). "
            "Investimi kthehet brenda 5-8 vitesh. "
            "Apliko pranë Ministrisë së Ekonomisë ose instaluesve të certifikuar. "
            "Programi mbështetet edhe nga fondet IPA të BE-së."
        ),
    },
    {
        "title_mk": "Grant per efiçiencë energjetike — Izolimi i ndërtesave",
        "domain": "ambient",
        "item_type": "grant",
        "institution": "Ministria e Mjedisit dhe Planifikimit Hapësinor (MOEPP) + UNDP",
        "source_url": "https://moepp.gov.mk/mk/efikasnost/",
        "budget": "deri 50% e kostos, max 200,000 denarë",
        "eligible_who": (
            "Pronarët e ndërtesave rezidenciale (shtëpi dhe pallate). "
            "Bashkëpronaret e pallateve (duhet shumicë e banorëve). "
            "Ndërtesat publike (shkolla, klinika). "
            "Prioritet për zonat me ndotje të lartë (Tetovë, Gostivar, Kërçovë)."
        ),
        "documents": (
            "Kartë identiteti e pronarit\n"
            "Dokumentet e pronësisë\n"
            "Auditim energjetik i ndërtesës (nga firmë e certifikuar)\n"
            "Oferta nga kontraktorë të certifikuar\n"
            "Vendim i kuvendi i pallatit (nëse pallat)\n"
            "Formulari i aplikimit MOEPP"
        ),
        "description": (
            "MOEPP dhe UNDP ofrojnë grante për izolimin termik të ndërtesave — "
            "kjo ul ngrohjen me 40-60% dhe ndihmon mjedisin. "
            "Programi është i rëndësishëm veçanërisht për Tetovën dhe Gostivarín "
            "ku ndotja ajrore nga ngrohja është problem serioz. "
            "Ndërhyrjet mbulojnë: izolim fasade, dritare, çati, sistem ngrohjeje. "
            "Apliko pranë MOEPP ose komunës tënde. "
            "Shpesh bashkë-financohen nga UNDP dhe GEF (fondi global mjedisor)."
        ),
    },
    {
        "title_mk": "Grante per bizneset e gjelberta — Ekonomia qarkulluese",
        "domain": "ambient",
        "item_type": "grant",
        "institution": "Fondi për Inovacione dhe Zhvillim Teknologjik (FITR) + MOEPP",
        "source_url": "https://fitr.mk/zelena-ekonomija/",
        "budget": "200,000 deri 3,000,000 denarë",
        "eligible_who": (
            "Bizneset që implementojnë teknologji të gjelberta. "
            "Startup-et në fushën e mjedisit dhe energjisë së rinovueshme. "
            "Bizneset që ulin mbetjet dhe emisionet CO2. "
            "Fermerët organikë dhe kooperativat eko-bujqësore."
        ),
        "documents": (
            "Certifikata e regjistrimit të biznesit\n"
            "Plan i projektit ekologjik\n"
            "Vlerësim i ndikimit mjedisor\n"
            "Buxhet i detajuar\n"
            "CV e ekipit\n"
            "Formulari i aplikimit FITR"
        ),
        "description": (
            "Grante për bizneset që ndërtojnë produkte ose shërbime miqësore me mjedisin: "
            "riciklim, kompostim, energji diellore/eolike, bujqësi organike, "
            "paketim biodegradabil, transport elektrik. "
            "Financohet nga FITR dhe fondet EU IPA. "
            "Thirrjet hapen 1-2 herë/vit — kontrollo fitr.mk. "
            "Ideal për ndërmarrje sociale dhe OJQ me aktivitet mjedisor."
        ),
    },
    {
        "title_mk": "Programi i pyllëzimit dhe mbrojtjes së pyjeve",
        "domain": "ambient",
        "item_type": "announcement",
        "institution": "Ministria e Bujqësisë, Pylltarisë dhe Ujrave (MBPU)",
        "source_url": "https://www.mbpei.gov.mk/mk/sumarstvo/",
        "budget": "falas (fidanë + mbështetje teknike) ose kompensim 3,000-8,000 denarë/ha",
        "eligible_who": (
            "Pronarët privatë të tokave të pyllëzueshme. "
            "Komunat dhe OJQ-të mjedisore. "
            "Fermerët me toka të paçelura në zona malore."
        ),
        "documents": (
            "Kartë identiteti\n"
            "Dokumentet e pronësisë ose marrëveshje me komunën\n"
            "Plani i pyllëzimit (hartohet me ndihmën e MBPU)\n"
            "Kërkesë me shkrim drejtuar Inspektoratit Pylltarë"
        ),
        "description": (
            "MBPU ofron fidanë falas dhe mbështetje teknike për pyllëzimin e tokave private. "
            "Pronarët që pyllëzojnë marrin kompensim vjetor (3,000-8,000 denarë/ha) "
            "për 5 vitet e para. "
            "Programi ndihmon edhe me parandalimin e erozionit dhe zjarrit. "
            "Apliko pranë Inspektoratit Rajonal të Pylltarisë ose komunës. "
            "OJQ-të mjedisore mund të organizojnë aksione pyllëzimi me ndihmë shtetërore."
        ),
    },
    {
        "title_mk": "Financim per projekte mjedisore — OJQ dhe komunitete",
        "domain": "ambient",
        "item_type": "grant",
        "institution": "MOEPP + UNDP + EU Delegacioni në RMV",
        "source_url": "https://moepp.gov.mk/mk/proekti/",
        "budget": "1,000 deri 50,000 EUR (varion sipas programit donator)",
        "eligible_who": (
            "OJQ-të mjedisore dhe sociale të regjistruara. "
            "Grupet joformale me mentor OJQ. "
            "Komunat dhe këshillat lokale. "
            "Shkollat dhe institucionet arsimore."
        ),
        "documents": (
            "Certifikata e regjistrimit të OJQ-së\n"
            "Propozim projekti (sipas formatit të donatorit)\n"
            "Buxhet i detajuar\n"
            "CV e koordinatorit\n"
            "Letër mbështetjeje nga partneri lokal\n"
            "Raportet financiare të vitit të kaluar"
        ),
        "description": (
            "MOEPP, UNDP dhe Delegacioni EU financojnë projekte mjedisore komunale: "
            "pastrimi i lumenjve dhe burimeve ujore, edukimi mjedisor në shkolla, "
            "krijimi i hapësirave të gjelbra, menaxhimi i mbetjeve, biodiversiteti. "
            "Grante nga 1,000 EUR (projektet e vogla) deri 50,000 EUR (projekte rajonale). "
            "Thirrjet publikohen tek moepp.gov.mk dhe undp.org/mk. "
            "House of Wisdom mund të aplikojë si OJQ e regjistruar."
        ),
    },
]

LIVE_SOURCES = [
    {"url": "https://moepp.gov.mk/", "institution": "Ministria e Mjedisit (MOEPP)", "domain": "ambient", "base": "https://moepp.gov.mk"},
]


class Command(BaseCommand):
    help = "Shto programet per mjedis dhe energji"

    def add_arguments(self, parser):
        parser.add_argument("--dry", action="store_true")
        parser.add_argument("--no-ai", action="store_true")

    def handle(self, *args, **options):
        self.dry = options["dry"]
        self.use_ai = not options["no_ai"] and bool(os.environ.get("GROQ_API_KEY"))
        gov_index = GovIndexPage.objects.live().first()
        if not gov_index:
            self.stderr.write(self.style.ERROR("Nuk u gjet GovIndexPage.")); return

        ai_client = self._init_ai() if self.use_ai else None
        total = 0

        self.stdout.write(self.style.HTTP_INFO(
            f"\n=== Programet Mjedisore & Energjetike ===\n"
            f"    {len(KNOWN_PROGRAMS)} programe | AI: {'aktiv' if ai_client else 'jo'}\n"
        ))

        for prog in KNOWN_PROGRAMS:
            url = prog["source_url"]
            if GovItemPage.objects.filter(source_url=url).exists():
                self.stdout.write(f"  [skip] {self._s(prog['title_mk'][:65])}"); continue
            if self.dry:
                self.stdout.write(f"  [DRY]  {prog['domain']} | {prog['item_type']}\n         {self._s(prog['title_mk'][:70])}")
                total += 1; continue
            data = self._enrich(ai_client, prog) if ai_client else self._fmt(prog)
            self._create(data, url, gov_index)
            total += 1
            self.stdout.write(self.style.SUCCESS(f"  [OK] {self._s(data['title'][:70])}"))

        # Live
        for source in LIVE_SOURCES:
            items = self._scrape(source["url"], source.get("base",""))
            for item in items[:4]:
                if GovItemPage.objects.filter(source_url=item["url"]).exists(): continue
                if self.dry:
                    self.stdout.write(f"  [DRY-LIVE] {self._s(item['title'][:65])}"); total+=1; continue
                detail = self._detail(item["url"])
                data = self._ai_live(ai_client, item, detail, source) if ai_client else None
                if data and data.get("title"):
                    if data.get("item_type") not in [c[0] for c in GovItemType.choices]: data["item_type"]="announcement"
                    if data.get("domain") not in [c[0] for c in ProgramDomain.choices]: data["domain"]="ambient"
                    self._create(data, item["url"], gov_index); total+=1

        s = self.style.WARNING if self.dry else self.style.SUCCESS
        self.stdout.write(s(f"\n[{'DRY' if self.dry else 'DONE'}] {total} programe mjedisore.\n"))

    def _enrich(self, client, prog):
        prompt = f"""Perkthe per shqiptaret e Maqedonise:
PROGRAMI: {prog['title_mk']}
INSTITUCIONI: {prog['institution']}
BUXHETI: {prog['budget']}
KUSH: {prog['eligible_who']}
PERSHKRIMI: {prog['description']}
JSON: {{"title":"shqip max 100 kar","simple_explanation":"<p>120-150 fjale...</p>"}}"""
        try:
            from groq import Groq
            msg = client.chat.completions.create(model=GROQ_MODEL, max_tokens=600,
                messages=[{"role":"user","content":prompt}])
            raw = re.sub(r"```(?:json)?","",msg.choices[0].message.content.strip()).strip("`").strip()
            raw = re.sub(r",\s*([}\]])",r"\1",raw)
            m = re.search(r"\{[\s\S]*\}",raw)
            if m:
                d = json.loads(m.group())
                return {"title":d.get("title",prog["title_mk"][:100]),"domain":prog["domain"],
                        "item_type":prog["item_type"],"institution":prog["institution"],
                        "simple_explanation":d.get("simple_explanation",f"<p>{prog['description']}</p>"),
                        "eligible_who":prog["eligible_who"],"documents_required":prog["documents"],"budget":prog["budget"]}
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"    [!] AI: {str(e)[:60]}"))
        return self._fmt(prog)

    def _fmt(self, prog):
        return {"title":prog["title_mk"][:100],"domain":prog["domain"],"item_type":prog["item_type"],
                "institution":prog["institution"],"simple_explanation":f"<p>{prog['description']}</p>",
                "eligible_who":prog["eligible_who"],"documents_required":prog["documents"],"budget":prog["budget"]}

    def _ai_live(self, client, item, detail, source):
        if not client: return None
        try:
            from groq import Groq
            prompt = f"""JSON per shqiptaret RMV:
TITULLI: {item['title']}
PERMBAJTJA: {detail.get('text','')[:500]}
{{"title":"shqip","domain":"ambient","item_type":"announcement","institution":"{source['institution']}","simple_explanation":"<p>...</p>","eligible_who":"","documents_required":"","budget":""}}"""
            msg = client.chat.completions.create(model=GROQ_MODEL, max_tokens=500,
                messages=[{"role":"user","content":prompt}])
            raw = re.sub(r"```(?:json)?","",msg.choices[0].message.content.strip()).strip("`").strip()
            raw = re.sub(r",\s*([}\]])",r"\1",raw)
            m = re.search(r"\{[\s\S]*\}",raw)
            if m: return json.loads(m.group())
        except Exception: pass
        return None

    def _scrape(self, url, base=""):
        try:
            r = requests.get(url, timeout=12, verify=False, headers={"User-Agent":"Mozilla/5.0"})
            r.encoding="utf-8"
            soup = BeautifulSoup(r.text,"html.parser")
            items, seen = [], set()
            for a in soup.find_all("a",href=True):
                href,text = a["href"],a.get_text(strip=True)
                if len(text)<20: continue
                if href.startswith("/"): href=(base or url.rstrip("/"))+href
                if href.startswith("http") and href not in seen and href!=url:
                    seen.add(href); items.append({"title":text[:200],"url":href})
            return items
        except Exception: return []

    def _detail(self, url):
        try:
            r = requests.get(url, timeout=10, verify=False, headers={"User-Agent":"Mozilla/5.0"})
            r.encoding="utf-8"; soup=BeautifulSoup(r.text,"html.parser")
            for t in soup(["script","style","nav","footer"]): t.decompose()
            return {"text":" ".join(soup.get_text(" ",strip=True).split())[:2000]}
        except Exception: return {"text":""}

    def _create(self, data, url, gov_index):
        gov_index = GovIndexPage.objects.live().get(pk=gov_index.pk)
        slug = self._slug(slugify(data["title"])[:80] or "program-mjedisor", gov_index)
        page = GovItemPage(title=data["title"],slug=slug,item_type=data.get("item_type","announcement"),
            domain=data.get("domain","ambient"),status=GovItemStatus.ACTIVE,
            institution=data.get("institution",""),budget=data.get("budget",""),
            eligible_who=data.get("eligible_who",""),documents_required=data.get("documents_required",""),
            original_url=url,source_url=url,simple_explanation=data.get("simple_explanation",""))
        gov_index.add_child(instance=page); page.save_revision().publish()

    def _slug(self, base, parent):
        slug, n = base, 1
        while Page.objects.filter(slug=slug,path__startswith=parent.path).exists():
            slug=f"{base}-{n}"; n+=1
        return slug

    def _init_ai(self):
        try:
            from groq import Groq; key=os.environ.get("GROQ_API_KEY","")
            return Groq(api_key=key) if key else None
        except ImportError: return None

    def _s(self, text):
        return str(text).encode("ascii",errors="replace").decode("ascii")
