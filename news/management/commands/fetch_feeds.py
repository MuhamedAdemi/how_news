"""
Management command: python manage.py fetch_feeds

Merr lajmet nga të gjitha RSS feed-et aktive dhe krijon artikuj në Wagtail.
Mund ta ekzekutosh manualisht ose ta planifikosh me Windows Task Scheduler.
"""
import feedparser
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

from wagtail.models import Page

from news.models import FeedSource, NewsArticlePage, NewsIndexPage


class Command(BaseCommand):
    help = "Merr lajmet nga RSS feed-et aktive dhe krijon artikuj"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Numri maksimal i lajmeve për çdo feed (default: 10)",
        )
        parser.add_argument(
            "--feed",
            type=str,
            help="Merr vetëm nga ky feed (emri i burimit)",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        specific_feed = options.get("feed")

        # Gjej faqen NewsIndexPage ku do të krijohen artikujt
        try:
            news_index = NewsIndexPage.objects.live().first()
        except NewsIndexPage.DoesNotExist:
            self.stderr.write(self.style.ERROR(
                "Nuk u gjet NewsIndexPage. Krijo një nga paneli Wagtail admin së pari."
            ))
            return

        if not news_index:
            self.stderr.write(self.style.ERROR(
                "Nuk u gjet NewsIndexPage. Krijo një nga paneli Wagtail admin së pari."
            ))
            return

        # Merr feed-et aktive
        sources = FeedSource.objects.filter(is_active=True)
        if specific_feed:
            sources = sources.filter(name__icontains=specific_feed)

        if not sources.exists():
            self.stdout.write(self.style.WARNING("Nuk ka feed burime aktive."))
            return

        total_created = 0

        for source in sources:
            self.stdout.write(f"\n[>>] Duke marre: {source.name} ({source.feed_url})")

            try:
                # Ri-merr news_index nga DB para cdo burimi per te shmangur cache probleme
                news_index = NewsIndexPage.objects.live().get(pk=news_index.pk)
                created = self._fetch_source(source, news_index, limit)
                total_created += created
                self.stdout.write(self.style.SUCCESS(f"   [OK] {created} artikuj te rinj"))

                source.last_fetched = timezone.now()
                source.save(update_fields=["last_fetched"])

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"   [ERR] Gabim: {e}"))

        self.stdout.write(self.style.SUCCESS(
            f"\n[DONE] Gjithsej {total_created} artikuj te rinj u krijuan."
        ))

    def _fetch_source(self, source, news_index, limit):
        """Merr dhe përpunon një RSS feed."""
        feed = feedparser.parse(source.feed_url)

        if feed.bozo:
            # feedparser.bozo = True kur ka problem me feed-in
            self.stdout.write(self.style.WARNING(
                "   [!] Feed ka probleme formatimi, po provojme gjithsesi..."
            ))

        created_count = 0
        entries = feed.entries[:limit]

        for entry in entries:
            url = getattr(entry, "link", "")
            title = getattr(entry, "title", "Pa titull")

            if not url:
                continue

            # Kontrollo nëse artikulli ekziston tashmë (shmang duplikatet)
            if NewsArticlePage.objects.filter(source_url=url).exists():
                continue

            # Merr tekstin hyrës (summary ose description)
            intro = ""
            if hasattr(entry, "summary"):
                # Hiq HTML tags nga summary
                import re
                intro = re.sub(r"<[^>]+>", "", entry.summary)[:400].strip()

            # Krijo slug unik nga titulli
            base_slug = slugify(title)[:80] or "lajm"
            slug = self._unique_slug(base_slug, news_index)

            # Krijo artikullin si fëmijë i NewsIndexPage
            article = NewsArticlePage(
                title=title,
                slug=slug,
                intro=intro,
                source_url=url,
                source_name=source.name,
                body=[],  # Trupi bosh — vetëm intro nga RSS
            )

            # Wagtail kërkon add_child për të vendosur faqen në pemë
            news_index.add_child(instance=article)

            # Publiko menjëherë
            revision = article.save_revision()
            revision.publish()

            created_count += 1

        return created_count

    def _unique_slug(self, base_slug, parent):
        """Gjeneron slug unik nëse ekziston tashmë."""
        slug = base_slug
        counter = 1
        while Page.objects.filter(slug=slug, path__startswith=parent.path).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug
