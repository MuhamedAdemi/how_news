"""
Management command: python manage.py fetch_mls

Merr thirrjet publike nga mls.gov.mk (Ministria e Punës dhe Politikes Sociale)
dhe krijon GovItemPage me domain=social/punesim.

Perdorim:
    python manage.py fetch_mls              # kerkon te gjitha thirrjet
    python manage.py fetch_mls --dry        # shfaq pa ruajtur
    python manage.py fetch_mls --limit 10   # max 10 thirrje
"""
import json
import os
import re
import warnings
from datetime import datetime

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

BASE_URL = "https://mls.gov.mk"
CALLS_URL = "https://mls.gov.mk/mk/odnosi-so-javnost/javni-povici"
CALLS_URL_EN = "https://mls.gov.mk/en-GB/odnosi-so-javnost/javni-povici"

GROQ_MODEL = "llama-3.3-70b-versatile"

DOMAIN_KEYWORDS = {
    "bujqesi": ["bujqësi", "bujqesi", "fermer", "tokë", "bimë", "harvest", "agrar"],
    "blegtori": ["blegtori", "bagëti", "dele", "lopë", "kafshë", "livestock"],
    "rural": ["rural", "fshat", "IPARD", "LEADER", "zhvillim vendor"],
    "social": ["sociale", "familje", "fëmijë", "pension", "invalid", "ndihm"],
    "punesim": ["punësim", "punë", "papunësi", "trajnim", "punëdhënës", "punëkërkues"],
    "biznes": ["biznes", "ndërmarrje", "SME", "startup", "eksport", "invest"],
    "ambient": ["ambient", "ekolog", "mjedis", "energji", "klimë"],
    "arsim": ["arsim", "edukim", "rini", "student", "shkollë", "bursë"],
}


class Command(BaseCommand):
    help = "Merr thirrjet publike nga mls.gov.mk"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--dry", action="store_true", help="Shfaq pa ruajtur")
        parser.add_argument("--no-ai", action="store_true", help="Pa AI, vetem scraping")

    def _safe(self, text):
        """Konverton karaktere speciale per terminal Windows."""
        return text.encode("ascii", errors="replace").decode("ascii")

    def handle(self, *args, **options):
        self.dry = options["dry"]
        self.use_ai = not options["no_ai"] and bool(os.environ.get("GROQ_API_KEY"))
        self.limit = options["limit"]

        self.stdout.write(self.style.HTTP_INFO(
            f"\n=== fetch_mls: Thirrjet Publike MLS ===\n"
            f"    AI: {'aktiv' if self.use_ai else 'jo'} | Dry: {self.dry}\n"
        ))

        gov_index = GovIndexPage.objects.live().first()
        if not gov_index:
            self.stderr.write(self.style.ERROR("Nuk u gjet GovIndexPage. Ekzekuto setup_site."))
            return

        ai_client = self._init_ai() if self.use_ai else None

        calls = self._scrape_call_list()
        self.stdout.write(f"    Gjeta {len(calls)} thirrje ne liste\n")

        created = 0
        for call in calls[:self.limit]:
            if GovItemPage.objects.filter(source_url=call["url"]).exists():
                self.stdout.write(f"  [skip] {self._safe(call['title'][:70])}")
                continue

            self.stdout.write(f"\n  [>>] {self._safe(call['title'][:70])}")

            detail = self._scrape_detail(call["url"])
            if ai_client:
                data = self._ai_process(ai_client, call, detail)
            else:
                data = self._basic_data(call, detail)

            if not data:
                continue

            if self.dry:
                self.stdout.write(f"       [DRY] Domain: {data['domain']} | Lloji: {data['item_type']}")
                self.stdout.write(f"       Kush: {self._safe(data.get('eligible_who', '')[:80])}")
                continue

            self._create_page(data, call["url"], gov_index)
            created += 1
            self.stdout.write(self.style.SUCCESS(f"       [OK] Krijua: {self._safe(data['title'][:60])}"))

        if not self.dry:
            self.stdout.write(self.style.SUCCESS(f"\n[DONE] {created} thirrje te reja nga MLS.\n"))

    def _scrape_call_list(self):
        """Merr listen e thirrjeve publike nga faqja kryesore."""
        calls = []
        for url in [CALLS_URL, CALLS_URL_EN]:
            try:
                r = requests.get(url, timeout=15, verify=False,
                                 headers={"User-Agent": "Mozilla/5.0 (compatible; HoWBot/1.0)"})
                r.encoding = "utf-8"
                soup = BeautifulSoup(r.text, "html.parser")

                # MLS perdor strukturen e zakonshme Drupal/CMS
                for selector in [
                    "article", ".views-row", ".node--type-javni-povik",
                    ".field--name-title a", "h3 a", "h2 a",
                    ".javni-povik a", ".view-content .views-row"
                ]:
                    items = soup.select(selector)
                    if items:
                        for item in items:
                            link = item.find("a") if item.name != "a" else item
                            if not link:
                                continue
                            href = link.get("href", "")
                            if not href:
                                continue
                            if href.startswith("/"):
                                href = BASE_URL + href
                            title = link.get_text(strip=True)[:200]
                            if title and href and "javni" in href.lower() or "povik" in href.lower() or len(title) > 15:
                                calls.append({"title": title, "url": href})
                        if calls:
                            return calls

                # Fallback: gjej te gjitha linqet qe duken si thirrje
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    text = a.get_text(strip=True)
                    if len(text) > 20 and any(
                        w in href.lower() for w in ["povik", "oglas", "konkurs", "tender"]
                    ):
                        if href.startswith("/"):
                            href = BASE_URL + href
                        calls.append({"title": text[:200], "url": href})

                if calls:
                    return calls
            except Exception as exc:
                self.stderr.write(self.style.WARNING(f"  [!] {url}: {exc}"))

        return calls

    def _scrape_detail(self, url):
        """Merr permbajtjen e plote te nje thirrjeje."""
        try:
            r = requests.get(url, timeout=12, verify=False,
                             headers={"User-Agent": "Mozilla/5.0"})
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")

            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            main = soup.find(["article", "main", ".field--body", ".node__content", "#content"])
            text = (main or soup).get_text(" ", strip=True)
            text = " ".join(text.split())[:3000]

            # Kërko afatin
            deadline = ""
            deadline_patterns = [
                r"rok[^\d]*(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
                r"afat[^\d]*(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
                r"do\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
                r"(\d{1,2}[./]\d{1,2}[./]\d{4})",
            ]
            for pattern in deadline_patterns:
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    deadline = m.group(1)
                    break

            return {"text": text, "deadline_raw": deadline}
        except Exception:
            return {"text": "", "deadline_raw": ""}

    def _ai_process(self, client, call, detail):
        """AI klasifikon, perkthen dhe strukturon thirrjen."""
        from groq import Groq

        domain_list = ", ".join([f"{k}({v})" for k, v in [
            ("bujqesi", "bujqësi/ferma"),
            ("blegtori", "kafshë/bagëti"),
            ("rural", "zhvillim rural/IPARD"),
            ("social", "ndihma sociale/familje"),
            ("punesim", "punësim/trajnim"),
            ("biznes", "biznes/SME"),
            ("ambient", "mjedis/energji"),
            ("arsim", "arsim/rini"),
            ("tjeter", "tjetër"),
        ]])

        prompt = f"""Ti je analist per platformen "HoW Voices" per shqiptaret e Maqedonise se Veriut.

Kjo eshte nje thirrje publike nga Ministria e Punes dhe Politikes Sociale (MLS) e Maqedonise:

TITULLI (mund te jete maqedonisht): {call['title']}
PERMBAJTJA: {detail['text'][:1500]}
AFATI I GJETUR: {detail['deadline_raw'] or 'nuk u gjet'}
URL: {call['url']}

Detyrat:
1. Perkthe/formuloje titullin ne Shqip te qarte (max 120 karaktere)
2. Identifiko domenin: {domain_list}
3. Shkruaj shpjegim 100-150 fjale per qytetaret shqiptare
4. Nxirr: kush ka te drejte te aplikoje (eligible_who)
5. Listo dokumentet e nevojshme (nje per rresht)
6. Identifiko llojin: grant, tender, competition, subsidy, announcement, loan
7. Nxirr institucioni dhe buxhetin nese ka
8. Afatin nese gjendet

Pergjigju VETEM me JSON:
{{
  "title": "titulli ne shqip",
  "domain": "punesim",
  "item_type": "grant",
  "institution": "Ministria e Punës dhe Politikës Sociale",
  "simple_explanation": "<p>shpjegim per qytetaret...</p>",
  "eligible_who": "kush ka te drejte...",
  "documents_required": "Kartes identiteti\\nCertifikata...",
  "budget": "",
  "deadline_text": ""
}}"""

        try:
            msg = client.chat.completions.create(
                model=GROQ_MODEL,
                max_tokens=900,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.choices[0].message.content.strip()
            raw = re.sub(r"```(?:json)?", "", raw).strip("`").strip()
            raw = re.sub(r"\bTrue\b", "true", raw)
            raw = re.sub(r"\bFalse\b", "false", raw)
            raw = re.sub(r"\bNone\b", "null", raw)
            raw = re.sub(r",\s*([}\]])", r"\1", raw)
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                return self._basic_data(call, detail)
            data = json.loads(match.group())

            valid_domains = [c[0] for c in ProgramDomain.choices]
            if data.get("domain") not in valid_domains:
                data["domain"] = self._guess_domain(call["title"] + " " + detail["text"])

            valid_types = [c[0] for c in GovItemType.choices]
            if data.get("item_type") not in valid_types:
                data["item_type"] = "announcement"

            return data
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"        [!] AI: {exc}"))
            return self._basic_data(call, detail)

    def _basic_data(self, call, detail):
        return {
            "title": call["title"][:200],
            "domain": self._guess_domain(call["title"] + " " + detail.get("text", "")),
            "item_type": "announcement",
            "institution": "Ministria e Punës dhe Politikës Sociale",
            "simple_explanation": f"<p>{detail.get('text', '')[:400]}</p>",
            "eligible_who": "",
            "documents_required": "",
            "budget": "",
        }

    def _guess_domain(self, text):
        text_lower = text.lower()
        for domain, keywords in DOMAIN_KEYWORDS.items():
            if any(k in text_lower for k in keywords):
                return domain
        return "tjeter"

    def _create_page(self, data, url, gov_index):
        gov_index = GovIndexPage.objects.live().get(pk=gov_index.pk)
        slug = self._unique_slug(slugify(data["title"])[:80] or "thirrje", gov_index)

        page = GovItemPage(
            title=data["title"],
            slug=slug,
            item_type=data.get("item_type", "announcement"),
            domain=data.get("domain", "tjeter"),
            status=GovItemStatus.ACTIVE,
            institution=data.get("institution", "MLS"),
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
