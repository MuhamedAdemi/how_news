"""
Management command: python manage.py fetch_education

Merr programet arsimore, bursat dhe trajnimet nga:
  - Baze e kuruar: bursa shtetërore, kredi studentore, programe rinie
  - mon.gov.mk: Ministria e Arsimit dhe Shkencës
  - bro.gov.mk: Byroja për Zhvillim të Arsimit
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
        "title_mk": "Bursë shtetërore për studentët — Kushtet dhe aplikimi",
        "domain": "arsim",
        "item_type": "grant",
        "institution": "Ministria e Arsimit dhe Shkencës (MON)",
        "source_url": "https://mon.gov.mk/mk/uchenichestvo-i-studentstvo/stipendii/",
        "budget": "3,000-8,000 denarë/muaj (varion sipas kategorisë)",
        "eligible_who": (
            "Studentët e regjistruar në universitetet publike të RMV. "
            "Kushtet kryesore: mesatare mbi 8.00, gjendje sociale e dobët (ose merit). "
            "Bursa sociale: familje me të ardhura nën pragun minimal. "
            "Bursa merite: studentët me rezultate të shkëlqyera pa kriter financiar. "
            "Studentët shqiptarë kanë kuotë të dedikuar."
        ),
        "documents": (
            "Certifikata e studentit (nga sekretaria e fakultetit)\n"
            "Transkript notash (mesatare e vitit të kaluar)\n"
            "Vërtetim i të ardhurave familjare (ose deklaratë tatimore)\n"
            "Certifikata e gjendjes civile\n"
            "Fotokopje e librezës bankare\n"
            "Formulari i aplikimit MON (online: e-uslugi.gov.mk)"
        ),
        "description": (
            "MON jep bursa mujore për studentët e shkëlqyer dhe/ose me gjendje të vështirë "
            "ekonomike. Ka dy kategori: "
            "Bursa sociale (3,000-5,000 denarë/muaj) — për familje me të ardhura të ulëta; "
            "Bursa merite (5,000-8,000 denarë/muaj) — për studentët me mesatare shumë të lartë. "
            "Aplikimet hapen zakonisht Tetor-Nëntor çdo vit. "
            "Apliko online te e-uslugi.gov.mk ose pranë fakultetit tënd."
        ),
    },
    {
        "title_mk": "Kredi studentore — Financim i arsimit të lartë",
        "domain": "arsim",
        "item_type": "loan",
        "institution": "Ministria e Arsimit dhe Shkencës (MON) + Banka Zhvillimore MBDP",
        "source_url": "https://mon.gov.mk/mk/studentski-krediti/",
        "budget": "deri 60,000 denarë/vit studimi, normë interesi 0-2%",
        "eligible_who": (
            "Studentët e regjistruar në universitetet publike dhe private të akredituara. "
            "Pa kriter mesatare të detyrueshme. "
            "Kthimi fillon 12 muaj pas përfundimit të studimeve. "
            "Garantues: prind ose kujdestar."
        ),
        "documents": (
            "Certifikata e studentit\n"
            "Kartë identiteti\n"
            "Kartë identiteti e garantuesit (prind/kujdestar)\n"
            "Vërtetim i të ardhurave të garantuesit\n"
            "Numër bankar student\n"
            "Formulari i aplikimit (MON ose MBDP)"
        ),
        "description": (
            "Studentët mund të marrin kredi studentore me normë shumë të ulët interesi (0-2%) "
            "për të mbuluar tarifat e studimit, librat dhe jetesën. "
            "Shuma deri 60,000 denarë/vit. Kthimi fillon 12 muaj pas diplomimit. "
            "Afati i kthimit deri 5 vjet. "
            "Apliko pranë sekretarisë së universitetit ose direkt te MBDP. "
            "Ky program është ideal për studentët pa mundësi financiare."
        ),
    },
    {
        "title_mk": "Bursa per studentet e pasardhesve te deshmoreve dhe invalideve te luftes",
        "domain": "arsim",
        "item_type": "grant",
        "institution": "Ministria e Punës dhe Politikës Sociale (MTSP)",
        "source_url": "https://mtsp.gov.mk/mk/stipendii-borci/",
        "budget": "5,000-7,000 denarë/muaj",
        "eligible_who": (
            "Fëmijët e dëshmorëve dhe invalidëve të luftës së RMV 2001. "
            "Studentët e regjistruar në universitetin publik. "
            "Pa kriter mesatare — automatik nëse plotëson kushtin familjar."
        ),
        "documents": (
            "Certifikata e studentit\n"
            "Vërtetim i statusit të familjes (nga MTSP)\n"
            "Kartë identiteti\n"
            "Numër bankar"
        ),
        "description": (
            "Fëmijët e dëshmorëve dhe invalidëve të luftës 2001 kanë të drejtë automatike "
            "për bursë mujore të garantuar nga shteti gjatë tërë studimeve. "
            "Shuma është 5,000-7,000 denarë/muaj. "
            "Apliko pranë Ministrisë së Punës dhe Politikës Sociale (MTSP) "
            "ose Qendrës për Punë Sociale në komunën tënde."
        ),
    },
    {
        "title_mk": "Regjistrim ne universitete publike — Procedura dhe afatet",
        "domain": "arsim",
        "item_type": "announcement",
        "institution": "Universitetet Publike të RMV (UKIM, UKLO, UGD, SEEU, DUT)",
        "source_url": "https://mon.gov.mk/mk/upisuvanje/",
        "budget": "Tarifa studimi: 6,000-18,000 denarë/vit (universitete publike)",
        "eligible_who": (
            "Maturantët me diplomë të gjimnazit ose shkollës së mesme profesionale. "
            "Transferimet nga universitete të tjera. "
            "Kuotat për shqiptarë: UKIM, SEEU (Tetovë), UKLO (Bitolë) kanë kuota të dedikuara. "
            "Studentët e huaj me njohje të diplomave."
        ),
        "documents": (
            "Diplomë e maturës (ose çertifikata e notave)\n"
            "Certifikata e lindjes\n"
            "Kartë identiteti\n"
            "Fotografi\n"
            "Dëshmi e pagesës së tarifës së aplikimit (zakonisht 300-500 denarë)\n"
            "Formular aplikimi (online ose fizikisht)"
        ),
        "description": (
            "Regjistrimi në universitetet publike bëhet 2 herë/vit: "
            "Sesioni i parë: Qershor-Korrik (pas maturës); "
            "Sesioni i dytë: Gusht-Shtator (nëse mbeten vende). "
            "Universitetet kryesore me programe shqipe: "
            "SEEU Tetovë (shumë fakultete në shqip), "
            "DUT Tetovë (Universiteti i Tetovës), "
            "UKIM Shkup (program dy gjuhësh). "
            "Tarifa vjetore për universitete publike: 6,000-18,000 denarë. "
            "Apliko online te e-uslugi.gov.mk ose direkt te universiteti."
        ),
    },
    {
        "title_mk": "Programet e rinjve dhe edukim joformal — Grante per OJQ",
        "domain": "arsim",
        "item_type": "grant",
        "institution": "Agjencia për Rini dhe Sport + EU Erasmus+ / Trup Europian i Solidaritetit",
        "source_url": "https://mio.gov.mk/mk/omladina/",
        "budget": "2,000 deri 150,000 EUR (Erasmus+); 1,000-15,000 EUR (programe kombëtare)",
        "eligible_who": (
            "OJQ-të rinore dhe organizatat e rinjve (18-30 vjeç). "
            "Grupet joformale me mbikëqyrje OJQ. "
            "Shkollat dhe qendrat arsimore. "
            "Projektet e mobilitetit ndërkombëtar (shkëmbime rinjsh me vendet EU)."
        ),
        "documents": (
            "Certifikata e regjistrimit të OJQ-së\n"
            "Propozim projekti (formati Erasmus+)\n"
            "Buxhet i detajuar\n"
            "CV e koordinatorit\n"
            "Letra e partnerit europian (për Erasmus+)\n"
            "Raportet e aktiviteteve të mëparshme"
        ),
        "description": (
            "Erasmus+ financon projekte rinore, shkëmbime, trajnime dhe partneritete "
            "arsimore. Thirrjet hapen 3 herë/vit (Janar, Maj, Tetor). "
            "Programi 'Trup Europian i Solidaritetit' dërgon/pret vullnetarë europianë. "
            "Programet kombëtare të Agjencisë për Rini financojnë aktivitete lokale "
            "rinore me grant deri 15,000 EUR. "
            "House of Wisdom si OJQ e regjistruar mund të aplikojë direkt."
        ),
    },
    {
        "title_mk": "Arsimi profesional dhe rikualifikimi — Programet e shkollave profesionale",
        "domain": "arsim",
        "item_type": "announcement",
        "institution": "Byroja për Zhvillim të Arsimit (BRO) + AVRM",
        "source_url": "https://bro.gov.mk/mk/",
        "budget": "Falas (financuar nga shteti) ose me tarife simbolike",
        "eligible_who": (
            "Të gjithë personat mbi 15 vjeç. "
            "Personat e papunë marrin prioritet (AVRM bashkëfinancim). "
            "Pa limit moshe për rikualifikim. "
            "Programet dyljore (dual education) me punëdhënës partner."
        ),
        "documents": (
            "Kartë identiteti\n"
            "Diplomë e shkollës fillore (minimum)\n"
            "Vërtetim nga AVRM (nëse i papunë)\n"
            "Formulari i aplikimit (shkolla profesionale)"
        ),
        "description": (
            "Shkollat profesionale publike ofrojnë trajnim 2-4 vjeçar në profesione me "
            "kërkesë të lartë: kuzhinier, elektricist, mekanik, infermier, IT, ndërtim. "
            "Arsimi është falas ose me tarife shumë të vogël. "
            "BRO bashkëpunon me AVRM — personat e papunë mund të financojnë rikualifikimin "
            "plotësisht pa pagesë. "
            "Programet dyljore: studenti punon gjysëm kohe te biznesi partner ndërkohë. "
            "Kontrollo shkollat profesionale në Tetovë, Gostivar dhe Kërçovë."
        ),
    },
]

LIVE_SOURCES = [
    {"url": "https://mon.gov.mk/", "institution": "Ministria e Arsimit (MON)", "domain": "arsim", "base": "https://mon.gov.mk"},
    {"url": "https://bro.gov.mk/", "institution": "Byroja për Zhvillim të Arsimit (BRO)", "domain": "arsim", "base": "https://bro.gov.mk"},
]


class Command(BaseCommand):
    help = "Shto programet arsimore, bursat dhe trajnimet"

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
            f"\n=== Programet Arsimore & Bursat ===\n"
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

        for source in LIVE_SOURCES:
            items = self._scrape(source["url"], source.get("base",""))
            self.stdout.write(f"  {source['url']}: {len(items)} linqe")
            for item in items[:3]:
                if GovItemPage.objects.filter(source_url=item["url"]).exists(): continue
                if self.dry:
                    self.stdout.write(f"  [DRY-LIVE] {self._s(item['title'][:65])}"); total+=1; continue
                detail = self._detail(item["url"])
                data = self._ai_live(ai_client, item, detail, source) if ai_client else None
                if data and data.get("title"):
                    if data.get("item_type") not in [c[0] for c in GovItemType.choices]: data["item_type"]="announcement"
                    if data.get("domain") not in [c[0] for c in ProgramDomain.choices]: data["domain"]="arsim"
                    self._create(data, item["url"], gov_index); total+=1

        s = self.style.WARNING if self.dry else self.style.SUCCESS
        self.stdout.write(s(f"\n[{'DRY' if self.dry else 'DONE'}] {total} programe arsimore.\n"))

    def _enrich(self, client, prog):
        prompt = f"""Perkthe per shqiptaret e Maqedonise:
PROGRAMI: {prog['title_mk']}
INSTITUCIONI: {prog['institution']}
BUXHETI: {prog['budget']}
KUSH: {prog['eligible_who']}
PERSHKRIMI: {prog['description']}
JSON: {{"title":"shqip max 100 kar","simple_explanation":"<p>120-150 fjale per studentet...</p>"}}"""
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
{{"title":"shqip","domain":"arsim","item_type":"announcement","institution":"{source['institution']}","simple_explanation":"<p>...</p>","eligible_who":"","documents_required":"","budget":""}}"""
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
            r.encoding="utf-8"; soup=BeautifulSoup(r.text,"html.parser")
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
        slug = self._slug(slugify(data["title"])[:80] or "program-arsimor", gov_index)
        page = GovItemPage(title=data["title"],slug=slug,item_type=data.get("item_type","announcement"),
            domain=data.get("domain","arsim"),status=GovItemStatus.ACTIVE,
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
