"""
Management command: python manage.py fetch_gov

Merr njoftimet qeveritare nga burime aktive dhe krijon GovItemPage.
- Burimi RSS (portalb.mk): AI filtron per relevance qeveritare
- Burimi WEB (vlada.mk): scraping + AI perkthen nga Maqedonisht

Perdorim:
    python manage.py fetch_gov            # pa AI, vetem RSS basic
    python manage.py fetch_gov --ai       # me LLaMA AI via Groq (kerkon GROQ_API_KEY)
    python manage.py fetch_gov --limit 5  # max 5 artikuj per burim
"""
import json
import re
import warnings

import feedparser
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

from wagtail.models import Page

from government.models import (
    GovIndexPage,
    GovItemPage,
    GovItemStatus,
    GovItemType,
    GovSource,
)

warnings.filterwarnings("ignore")  # supreson SSL warnings per gov sites

GROQ_MODEL = "llama-3.1-8b-instant"

GOV_KEYWORDS = [
    "konkurs", "tender", "grant", "fond", "buxhet", "financim",
    "aplikim", "thirrje", "subvencion", "ligj", "dekret", "vendim",
    "ministri", "qeveri", "komunal", "publik", "shtet", "pension",
    "ndihm", "social", "punesim", "tatim", "docan",
]


class Command(BaseCommand):
    help = "Merr njoftimet qeveritare te RMV dhe krijon GovItemPage"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=5)
        parser.add_argument("--ai", action="store_true",
                            help="Perdor Claude AI per filtrim dhe shpjegim")
        parser.add_argument("--source", type=str)

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO(
            "\n=== fetch_gov: Qeveria e RMV ===\n"
        ))

        gov_index = GovIndexPage.objects.live().first()
        if not gov_index:
            self.stderr.write(self.style.ERROR(
                "Nuk u gjet GovIndexPage. Ekzekuto setup_site."
            ))
            return

        sources = GovSource.objects.filter(is_active=True)
        if options.get("source"):
            sources = sources.filter(name__icontains=options["source"])

        if not sources.exists():
            self.stdout.write(self.style.WARNING(
                "Nuk ka burime. Ekzekuto: python manage.py setup_site"
            ))
            return

        ai_client = None
        if options["ai"]:
            ai_client = self._init_ai()
            status = "[AI aktiv]" if ai_client else "[!] Pa AI key"
            self.stdout.write(self.style.SUCCESS(status) if ai_client
                              else self.style.WARNING(status))

        total = 0
        for source in sources:
            gov_index = GovIndexPage.objects.live().get(pk=gov_index.pk)
            self.stdout.write(f"\n[>>] {source.name}")
            try:
                is_web = source.url.endswith("/odnosi-so-javnost") or \
                         "vlada.mk" in source.url
                if is_web:
                    created = self._scrape_web(
                        source, gov_index, options["limit"], ai_client
                    )
                else:
                    created = self._fetch_rss(
                        source, gov_index, options["limit"], ai_client
                    )
                total += created
                self.stdout.write(self.style.SUCCESS(f"    [OK] {created} te rinj"))
                source.last_fetched = timezone.now()
                source.save(update_fields=["last_fetched"])
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"    [ERR] {exc}"))

        self.stdout.write(self.style.SUCCESS(
            f"\n[DONE] {total} GovItemPage te reja.\n"
        ))

    # ------------------------------------------------------------------
    # RSS (portalb.mk)
    # ------------------------------------------------------------------

    def _fetch_rss(self, source, gov_index, limit, ai_client):
        feed = feedparser.parse(source.url)
        created = 0

        for entry in feed.entries[:limit * 3]:  # fetch me shume, filtro pastaj
            url = getattr(entry, "link", "").strip()
            if not url or GovItemPage.objects.filter(source_url=url).exists():
                continue

            title = getattr(entry, "title", "").strip() or "Njoftim"
            body = ""
            if hasattr(entry, "summary"):
                body = re.sub(r"<[^>]+>", "", entry.summary)[:1000].strip()

            # Pa AI: filtro me keywords bazike
            if not ai_client:
                if not self._has_gov_keywords(title + " " + body):
                    continue
                data = self._basic_data(title, body, source)
            else:
                data = self._ai_process_rss(ai_client, title, body, source)
                if not data:
                    continue  # AI ka vendosur qe nuk eshte relevante

            self._create_page(data, url, gov_index)
            created += 1
            if created >= limit:
                break

        return created

    # ------------------------------------------------------------------
    # Web scraping (vlada.mk)
    # ------------------------------------------------------------------

    def _scrape_web(self, source, gov_index, limit, ai_client):
        try:
            r = requests.get(
                source.url, timeout=12, verify=False,
                headers={"User-Agent": "Mozilla/5.0 (compatible; HoWNewsBot/1.0)"},
            )
            r.encoding = "utf-8"
        except Exception as exc:
            raise RuntimeError(f"HTTP error: {exc}")

        soup = BeautifulSoup(r.text, "html.parser")
        created = 0

        # Gjej linqet e lajmeve (vlada.mk ka strukture <article> ose <h3><a>)
        articles = []
        for selector in ["article", ".views-row", ".node--type-vesti"]:
            found = soup.select(selector)
            if found:
                articles = found
                break

        # Fallback: gjej te gjitha linqet qe duken si URL lajmesh
        if not articles:
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                if "/mk-MK/" in href and any(
                    w in href for w in ["novost", "vest", "soopstenie", "press"]
                ):
                    articles.append(a)

        for item in articles[:limit * 2]:
            # Nxirr titullin dhe URL-ne
            if item.name == "a":
                link_tag = item
                title_text = item.text.strip()
            else:
                link_tag = item.find("a", href=True)
                title_text = (
                    item.find(["h2", "h3", "h4"]) or link_tag
                )
                title_text = title_text.text.strip() if title_text else ""

            if not link_tag or not title_text:
                continue

            href = link_tag.get("href", "")
            if href.startswith("/"):
                href = "https://vlada.mk" + href
            elif not href.startswith("http"):
                continue

            if GovItemPage.objects.filter(source_url=href).exists():
                continue

            # Shko te faqja e plote per me shume permbajtje (opsionale me AI)
            body_text = ""
            if ai_client:
                try:
                    r2 = requests.get(href, timeout=8, verify=False,
                                      headers={"User-Agent": "Mozilla/5.0"})
                    r2.encoding = "utf-8"
                    s2 = BeautifulSoup(r2.text, "html.parser")
                    content_div = s2.find(["article", ".field--body", "main"])
                    if content_div:
                        body_text = content_div.get_text(" ", strip=True)[:1500]
                except Exception:
                    pass

            if ai_client:
                data = self._ai_process_web(
                    ai_client, title_text, body_text, source
                )
                if not data:
                    continue
            else:
                data = self._basic_data(title_text, body_text, source)

            self._create_page(data, href, gov_index)
            created += 1
            if created >= limit:
                break

        return created

    # ------------------------------------------------------------------
    # Krijimi i GovItemPage
    # ------------------------------------------------------------------

    def _create_page(self, data, url, gov_index):
        slug = self._unique_slug(
            slugify(data["title"])[:80] or "njoftim", gov_index
        )
        page = GovItemPage(
            title=data["title"],
            slug=slug,
            item_type=data["item_type"],
            status=GovItemStatus.ACTIVE,
            institution=data["institution"],
            budget=data.get("budget", ""),
            original_url=url,
            source_url=url,
            simple_explanation=data["simple_explanation"],
        )
        gov_index.add_child(instance=page)
        rev = page.save_revision()
        rev.publish()

    # ------------------------------------------------------------------
    # AI — RSS filter + simplifikim
    # ------------------------------------------------------------------

    def _ai_process_rss(self, client, title, body, source):
        """Kthen dict nese relevante per Qeveria e Thjesht, None nese jo."""
        prompt = f"""Ti je filtrues per platformen "HoW News - Qeveria e Thjesht" per shqiptaret e Maqedonise se Veriut.

Lexo kete titull dhe permbajtje te artikullit:
TITULLI: {title}
PERMBAJTJA: {body[:600]}

PYETJA: A eshte ky artikull relevante per "Qeveria e Thjesht" - domethene: a permban informacion per tendere, grante, fonde, konkurse, ndihma sociale, ligje, rregullore, ose njoftime zyrtare qeveritare qe ndikojne ne jeten e qytetareve?

Nese JO -> pergjigju me: {{"relevant": false}}

Nese PO -> shkruaj:
{{
  "relevant": true,
  "title": "titulli i pershtatshme ne Shqip (max 100 karaktere)",
  "simple_explanation": "<p>Shpjegim 80-120 fjale ne Shqip per qytetaret - cfare ndodh, kush preket, cfare duhet bere nese ka afat</p>",
  "item_type": "tender|grant|competition|law|announcement",
  "institution": "institucioni pergjegjes",
  "budget": ""
}}

Pergjigju VETEM me JSON, asnje tekst tjeter."""

        try:
            msg = client.chat.completions.create(
                model=GROQ_MODEL,
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = self._clean_json(msg.choices[0].message.content.strip())
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                return None
            parsed = json.loads(match.group())
            if not parsed.get("relevant"):
                return None
            valid = [c[0] for c in GovItemType.choices]
            if parsed.get("item_type") not in valid:
                parsed["item_type"] = source.default_item_type
            parsed.setdefault("institution", source.institution)
            return parsed
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"        [!] AI: {exc}"))
            return None

    def _ai_process_web(self, client, title_mk, body_mk, source):
        """Perkthen nga Maqedonisht dhe krijon shpjegim shqip."""
        prompt = f"""Ti je asistent i "HoW News - Qeveria e Thjesht" per shqiptaret e Maqedonise se Veriut.

Ky njoftim eshte nga faqja zyrtare e Qeverise se RMV (ne gjuhe Maqedonase):
TITULLI: {title_mk}
PERMBAJTJA: {body_mk[:800] or '(pa permbajtje te detajuar)'}

Burimi: {source.institution}

Detyrat:
1. Perkthe titullin ne Shqip (qarte, max 100 karaktere)
2. Shkruaj shpjegim te thjeshte (80-130 fjale) per qytetaret shqiptare: cfare ndodh, kush preket, a ka afat
3. Identifiko llojin: tender, grant, competition, law, announcement
4. Nxirr institucionin (ne Shqip)
5. Nxirr buxhetin nese ka

Pergjigju VETEM me JSON:
{{
  "title": "titulli ne shqip",
  "simple_explanation": "<p>shpjegimi</p>",
  "item_type": "announcement",
  "institution": "institucioni",
  "budget": ""
}}"""

        try:
            msg = client.chat.completions.create(
                model=GROQ_MODEL,
                max_tokens=700,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = self._clean_json(msg.choices[0].message.content.strip())
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                return None
            parsed = json.loads(match.group())
            valid = [c[0] for c in GovItemType.choices]
            if parsed.get("item_type") not in valid:
                parsed["item_type"] = source.default_item_type
            parsed.setdefault("institution", source.institution)
            return parsed
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"        [!] AI: {exc}"))
            return self._basic_data(title_mk, body_mk, source)

    # ------------------------------------------------------------------
    # Ndihmoese
    # ------------------------------------------------------------------

    def _basic_data(self, title, body, source):
        return {
            "title": title[:200],
            "simple_explanation": (
                f"<p>{body[:400]}</p>" if body
                else "<p>Shiko linkun origjinal per me shume detaje.</p>"
            ),
            "item_type": source.default_item_type,
            "institution": source.institution,
            "budget": "",
        }

    def _has_gov_keywords(self, text):
        text_lower = text.lower()
        return any(kw in text_lower for kw in GOV_KEYWORDS)

    def _init_ai(self):
        try:
            import os
            from groq import Groq
            key = os.environ.get("GROQ_API_KEY", "")
            return Groq(api_key=key) if key else None
        except ImportError:
            return None

    def _clean_json(self, raw: str) -> str:
        """Pastron output-in e AI para json.loads — fix True/False/None dhe code fences."""
        raw = re.sub(r"```(?:json)?", "", raw).strip("`").strip()
        raw = re.sub(r"\bTrue\b", "true", raw)
        raw = re.sub(r"\bFalse\b", "false", raw)
        raw = re.sub(r"\bNone\b", "null", raw)
        raw = re.sub(r",\s*([}\]])", r"\1", raw)  # trailing commas
        return raw

    def _unique_slug(self, base_slug, parent):
        slug = base_slug
        counter = 1
        while Page.objects.filter(
            slug=slug, path__startswith=parent.path
        ).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug
