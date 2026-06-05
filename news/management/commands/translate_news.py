"""
python manage.py translate_news           # perkthe 30 artikuj pa perkthim
python manage.py translate_news --limit 50
python manage.py translate_news --all     # te gjithe (kujdes: shume API calls)
"""
import json, os, re
from django.core.management.base import BaseCommand
from news.models import NewsArticlePage
from news.management.commands.fetch_feeds import _translate_intro

class Command(BaseCommand):
    help = "Perkthe intro-t e artikujve ekzistues ne SQ/MK/EN"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=30)
        parser.add_argument("--all", action="store_true")

    def handle(self, *args, **options):
        if not os.environ.get("GROQ_API_KEY"):
            self.stderr.write(self.style.ERROR("GROQ_API_KEY mungon.")); return

        qs = NewsArticlePage.objects.live().filter(intro_sq="", intro__gt="")
        if not options["all"]:
            qs = qs[:options["limit"]]

        total = qs.count() if options["all"] else min(qs.count(), options["limit"])
        self.stdout.write(self.style.HTTP_INFO(f"\n=== translate_news: {total} artikuj ===\n"))

        done = 0
        for article in qs:
            t = _translate_intro(article.intro, article.language)
            if t:
                article.intro_sq = t.get("sq", "")
                article.intro_mk = t.get("mk", "")
                article.intro_en = t.get("en", "")
                article.save(update_fields=["intro_sq","intro_mk","intro_en"])
                done += 1
                if done % 10 == 0:
                    self.stdout.write(f"  {done}/{total}...")

        self.stdout.write(self.style.SUCCESS(f"\n[DONE] {done} artikuj u perkthyen.\n"))
