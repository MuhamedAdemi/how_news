"""
Management command: python manage.py process_url <URL>

Merr nje URL te nje faqeje qeveritare, e lexon me AI dhe krijon GovItemPage.
Kjo eshte "Rruga B" e automatizuar — redaktori jep URL, AI ben pjesen tjeter.

Perdorim:
    python manage.py process_url https://vlada.mk/mk-MK/...
    python manage.py process_url https://e-nabavki.gov.mk/... --type tender
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
)

warnings.filterwarnings("ignore")


class Command(BaseCommand):
    help = "Merr nje URL qeveritare, perdor AI per te krijuar GovItemPage"

    def add_arguments(self, parser):
        parser.add_argument("url", help="URL e faqes qeveritare")
        parser.add_argument(
            "--type",
            choices=[c[0] for c in GovItemType.choices],
            default="announcement",
            help="Lloji i parazgjedhur (default: announcement)",
        )

    def handle(self, *args, **options):
        url = options["url"]
        api_key = os.environ.get("GROQ_API_KEY", "")

        if not api_key:
            self.stderr.write(self.style.ERROR(
                "GROQ_API_KEY mungon ne .env (falas: console.groq.com)"
            ))
            return

        gov_index = GovIndexPage.objects.live().first()
        if not gov_index:
            self.stderr.write(self.style.ERROR("Nuk u gjet GovIndexPage."))
            return

        if GovItemPage.objects.filter(source_url=url).exists():
            self.stdout.write(self.style.WARNING(f"URL ekziston tashme: {url}"))
            return

        self.stdout.write(f"[>>] Duke lexuar: {url}")

        # Shkarko faqen
        try:
            r = requests.get(
                url, timeout=15, verify=False,
                headers={"User-Agent": "Mozilla/5.0 (compatible; HoWNewsBot/1.0)"},
            )
            r.encoding = "utf-8"
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"HTTP error: {exc}"))
            return

        soup = BeautifulSoup(r.text, "html.parser")

        # Nxirr tekstin kryesor
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        main = soup.find(["article", "main", ".content", "#content"])
        text = (main or soup).get_text(" ", strip=True)
        text = " ".join(text.split())[:2000]

        title_tag = soup.find(["h1", "h2"])
        raw_title = title_tag.text.strip()[:200] if title_tag else url

        self.stdout.write(f"    Titulli: {raw_title[:80]}")
        self.stdout.write("    [AI] Duke procesuar...")

        # Groq API (LLaMA 3.3 70B — falas)
        try:
            from groq import Groq
            client = Groq(api_key=api_key)

            prompt = f"""Ti je asistent i "HoW News - Qeveria e Thjesht" per shqiptaret e Maqedonise se Veriut.

Kjo eshte permbajtja e nje faqeje zyrtare qeveritare (mund te jete ne Maqedonisht ose Shqip):

TITULLI: {raw_title}

PERMBAJTJA:
{text}

BURIMI: {url}

Detyrat:
1. Perkthe/formuloje titullin ne Shqip te qarte (max 120 karaktere)
2. Shkruaj shpjegim te thjeshte (100-150 fjale) per qytetaret shqiptare: cfare eshte, kush preket, a ka afat/kushte
3. Identifiko: lloji (tender/grant/competition/law/announcement), institucioni, buxheti, afati
4. Nese teksti eshte ne Maqedonisht, perkthe dhe thjeshteso ne Shqip

Pergjigju VETEM me JSON:
{{
  "title": "titulli ne shqip",
  "simple_explanation": "<p>shpjegimi html</p>",
  "item_type": "announcement",
  "institution": "institucioni",
  "budget": "",
  "deadline_text": ""
}}"""

            msg = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=900,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.choices[0].message.content.strip()
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                raise ValueError("AI nuk ktheu JSON te vlefshme")

            data = json.loads(match.group())
            valid = [c[0] for c in GovItemType.choices]
            if data.get("item_type") not in valid:
                data["item_type"] = options["type"]

        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"AI error: {exc}"))
            return

        # Krijo GovItemPage
        slug = self._unique_slug(
            slugify(data["title"])[:80] or "njoftim", gov_index
        )
        gov_index = GovIndexPage.objects.live().get(pk=gov_index.pk)

        page = GovItemPage(
            title=data["title"],
            slug=slug,
            item_type=data["item_type"],
            status=GovItemStatus.ACTIVE,
            institution=data.get("institution", ""),
            budget=data.get("budget", ""),
            original_url=url,
            source_url=url,
            simple_explanation=data.get("simple_explanation", ""),
        )
        gov_index.add_child(instance=page)
        rev = page.save_revision()
        rev.publish()

        self.stdout.write(self.style.SUCCESS(
            f"\n[DONE] U krijua: {data['title']}\n"
            f"       Lloji: {data['item_type']} | "
            f"Institucioni: {data.get('institution', '—')}\n"
            f"       Shiko: /qeveria/"
        ))

    def _unique_slug(self, base_slug, parent):
        slug = base_slug
        counter = 1
        while Page.objects.filter(
            slug=slug, path__startswith=parent.path
        ).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug
