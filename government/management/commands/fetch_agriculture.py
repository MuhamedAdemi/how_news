"""
Management command: python manage.py fetch_agriculture

Merr programet bujqesore dhe subvencionet nga:
  - mbpei.gov.mk  (Ministria e Bujqesise, Pylltarise dhe Ujrave)
  - ipardpa.gov.mk (IPARD III — fondet EU per zhvillim rural)
  - afsard.gov.mk  (Agjensia per Mbeshtetje Financiare ne Bujqesi)

Perdorim:
    python manage.py fetch_agriculture              # te gjitha burimet
    python manage.py fetch_agriculture --source mbpei
    python manage.py fetch_agriculture --source ipard
    python manage.py fetch_agriculture --dry
    python manage.py fetch_agriculture --limit 10
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

SOURCES = {
    "mbpei": {
        "name": "MBPEI — Ministria e Bujqesise",
        "institution": "Ministria e Bujqësisë, Pylltarisë dhe Ujrave",
        "domain": ProgramDomain.AGRICULTURE,
        "urls": [
            "https://www.mbpei.gov.mk/mk/category/subvencii/",
            "https://www.mbpei.gov.mk/mk/category/finansiska-poddrska/",
            "https://www.mbpei.gov.mk/mk/agencii/afsard/",
            "https://www.mbpei.gov.mk/mk/",
        ],
    },
    "ipard": {
        "name": "IPARD III — Zhvillim Rural EU",
        "institution": "Agjensia per Zbatimin e IPARD (IPARD PA)",
        "domain": ProgramDomain.RURAL,
        "urls": [
            "https://ipardpa.gov.mk/mk/category/javni-povici/",
            "https://ipardpa.gov.mk/mk/",
            "https://ipardpa.gov.mk/",
        ],
    },
    "afsard": {
        "name": "AFSARD — Mbeshtetje Financiare Bujqesore",
        "institution": "Agjensia per Mbeshtetje Financiare ne Bujqësi dhe Zhvillim Rural (AFSARD)",
        "domain": ProgramDomain.AGRICULTURE,
        "urls": [
            "https://afsard.gov.mk/mk/",
            "https://www.afsard.gov.mk/",
        ],
    },
}


class Command(BaseCommand):
    help = "Merr programet bujqesore nga MBPEI, IPARD dhe AFSARD"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=15)
        parser.add_argument("--dry", action="store_true")
        parser.add_argument(
            "--source",
            choices=list(SOURCES.keys()) + ["all"],
            default="all",
            help="Burimi: mbpei, ipard, afsard ose all",
        )
        parser.add_argument("--no-ai", action="store_true")

    def handle(self, *args, **options):
        self.dry = options["dry"]
        self.limit = options["limit"]
        self.use_ai = not options["no_ai"] and bool(os.environ.get("GROQ_API_KEY"))

        gov_index = GovIndexPage.objects.live().first()
        if not gov_index:
            self.stderr.write(self.style.ERROR("Nuk u gjet GovIndexPage."))
            return

        ai_client = self._init_ai() if self.use_ai else None

        sources_to_run = (
            list(SOURCES.keys()) if options["source"] == "all"
            else [options["source"]]
        )

        total = 0
        for source_key in sources_to_run:
            source = SOURCES[source_key]
            self.stdout.write(self.style.HTTP_INFO(
                f"\n=== {source['name']} ===\n"
                f"    AI: {'aktiv' if ai_client else 'jo'} | Dry: {self.dry}\n"
            ))

            items = self._scrape_source(source)
            self.stdout.write(f"    Gjeta {len(items)} linqe\n")

            created = 0
            for item in items[:self.limit]:
                if GovItemPage.objects.filter(source_url=item["url"]).exists():
                    self.stdout.write(f"  [skip] {self._s(item['title'][:65])}")
                    continue

                self.stdout.write(f"\n  [>>] {self._s(item['title'][:65])}")
                detail = self._fetch_detail(item["url"])

                data = (
                    self._ai_process(ai_client, item, detail, source)
                    if ai_client
                    else self._basic_data(item, detail, source)
                )
                if not data:
                    continue

                if self.dry:
                    self.stdout.write(
                        f"       [DRY] {data['domain']} | {data['item_type']}\n"
                        f"       {self._s(data.get('eligible_who', '')[:80])}"
                    )
                    created += 1
                    continue

                self._create_page(data, item["url"], gov_index)
                created += 1
                self.stdout.write(self.style.SUCCESS(
                    f"       [OK] {self._s(data['title'][:60])}"
                ))

            total += created
            self.stdout.write(self.style.SUCCESS(f"\n    {created} te reja nga {source['name']}"))

        self.stdout.write(self.style.SUCCESS(f"\n[DONE] Gjithsej {total} programe bujqesore.\n"))

    # ── Scraping ──────────────────────────────────────────────────────────

    def _scrape_source(self, source):
        """Provo cdo URL derisa te gjesh linqe."""
        items = []
        for url in source["urls"]:
            try:
                r = requests.get(
                    url, timeout=15, verify=False,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; HoWBot/1.0)"},
                )
                r.encoding = "utf-8"
                soup = BeautifulSoup(r.text, "html.parser")

                # Strategji: selektoret e zakonshme ne faqe qeveritare maqedonase
                found = []
                for sel in [
                    "article h2 a", "article h3 a", ".views-row a",
                    ".node--type-page a", ".field--name-title a",
                    "h2 a", "h3 a", ".entry-title a",
                    ".post-title a", "li a",
                ]:
                    candidates = soup.select(sel)
                    for a in candidates:
                        href = a.get("href", "").strip()
                        text = a.get_text(strip=True)
                        if not href or not text or len(text) < 15:
                            continue
                        if href.startswith("/"):
                            base = url.split("/mk/")[0] if "/mk/" in url else url.rsplit("/", 1)[0]
                            href = base.rstrip("/") + "/" + href.lstrip("/")
                        if href.startswith("http") and href != url:
                            found.append({"title": text[:200], "url": href})

                    if len(found) >= 5:
                        break

                # Fallback: te gjitha linqet me titull te gjate
                if not found:
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        text = a.get_text(strip=True)
                        if len(text) < 20:
                            continue
                        if href.startswith("/"):
                            base = url.split("/mk/")[0] if "/mk/" in url else url.rsplit("/", 1)[0]
                            href = base.rstrip("/") + "/" + href.lstrip("/")
                        if href.startswith("http") and href != url:
                            found.append({"title": text[:200], "url": href})

                if found:
                    # Deduplikim
                    seen = set()
                    for f in found:
                        if f["url"] not in seen:
                            seen.add(f["url"])
                            items.append(f)
                    return items[:50]

            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"  [!] {url}: {self._s(str(exc)[:60])}"))

        return items

    def _fetch_detail(self, url):
        """Merr permbajtjen e plote."""
        try:
            r = requests.get(
                url, timeout=12, verify=False,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            main = soup.find(["article", "main", ".field--body", ".entry-content", "#content"])
            text = (main or soup).get_text(" ", strip=True)
            text = " ".join(text.split())[:3000]

            deadline = ""
            for pat in [
                r"rok[^\d]*(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
                r"do\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
                r"(\d{1,2}[./]\d{1,2}[./]\d{4})",
            ]:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    deadline = m.group(1)
                    break

            return {"text": text, "deadline_raw": deadline}
        except Exception:
            return {"text": "", "deadline_raw": ""}

    # ── AI Processing ─────────────────────────────────────────────────────

    def _ai_process(self, client, item, detail, source):
        prompt = f"""Ti je analist per "HoW Voices" — platformen per shqiptaret e Maqedonise se Veriut.

Ky program/subvencion eshte nga {source['institution']} (Maqedoni):

TITULLI: {item['title']}
PERMBAJTJA: {detail['text'][:2000]}
AFATI: {detail['deadline_raw'] or 'nuk u gjet'}
URL: {item['url']}

Detyrat:
1. Perkthe/formuloje titullin ne Shqip te qarte (max 120 karaktere)
2. Identifiko domenin: bujqesi(ferma/kultura), blegtori(kafsh/bageti), rural(IPARD/zhvillim), tjeter
3. Shkruaj shpjegim 120-160 fjale per fermerët shqiptarë — çfarë është, kush mund të marrë, sa jep
4. Nxirr kushtet e eligibilitetit (kush mund te aplikoje — siperfaqja min, lloji i aktivitetit, etj.)
5. Listo dokumentet (nje per rresht)
6. Lloji: grant, subsidy, tender, competition, announcement, loan
7. Shuma/buxheti nese ka
8. Afati nese ka

Pergjigju VETEM me JSON:
{{
  "title": "titulli shqip",
  "domain": "bujqesi",
  "item_type": "subsidy",
  "institution": "{source['institution']}",
  "simple_explanation": "<p>shpjegim per fermerët...</p>",
  "eligible_who": "Fermerë me të paktën 0.3 ha tokë bujqësore...",
  "documents_required": "Kartë identiteti\\nCertifikatë pronësie tokës\\nPlan biznesi",
  "budget": "deri 50% e vlerës",
  "deadline_text": ""
}}"""

        try:
            from groq import Groq
            msg = client.chat.completions.create(
                model=GROQ_MODEL,
                max_tokens=1000,
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
                return self._basic_data(item, detail, source)
            data = json.loads(match.group())

            valid_domains = [c[0] for c in ProgramDomain.choices]
            if data.get("domain") not in valid_domains:
                data["domain"] = source["domain"]

            valid_types = [c[0] for c in GovItemType.choices]
            if data.get("item_type") not in valid_types:
                data["item_type"] = "subsidy"

            return data
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"        [!] AI: {self._s(str(exc)[:80])}"))
            return self._basic_data(item, detail, source)

    def _basic_data(self, item, detail, source):
        return {
            "title": item["title"][:200],
            "domain": source["domain"],
            "item_type": "subsidy",
            "institution": source["institution"],
            "simple_explanation": f"<p>{detail.get('text', '')[:400]}</p>",
            "eligible_who": "",
            "documents_required": "",
            "budget": "",
        }

    # ── Krijimi i faqes ───────────────────────────────────────────────────

    def _create_page(self, data, url, gov_index):
        gov_index = GovIndexPage.objects.live().get(pk=gov_index.pk)
        slug = self._unique_slug(
            slugify(data["title"])[:80] or "program-bujqesor", gov_index
        )
        page = GovItemPage(
            title=data["title"],
            slug=slug,
            item_type=data.get("item_type", "subsidy"),
            domain=data.get("domain", ProgramDomain.AGRICULTURE),
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
        """Safe print per terminal Windows CP1252."""
        return str(text).encode("ascii", errors="replace").decode("ascii")
