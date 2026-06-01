"""
Management command: python manage.py setup_site

Ndërton strukturën fillestare të faqeve Wagtail dhe shton burimet RSS.
I sigurt për t'u ekzekutuar shumë herë — nuk krijon duplikate.

Struktura e krijuar:
  Root
  └── Home (HomePage)
      ├── lajme  (NewsIndexPage)
      ├── qeveria (GovIndexPage)
      └── video   (VideoIndexPage)
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from wagtail.models import Page, Site

from government.models import GovIndexPage
from home.models import HomePage
from news.models import FeedSource, FeedLanguage, NewsIndexPage
from videos.models import VideoIndexPage

DEFAULT_FEEDS = [
    {
        "name": "Telegrafi",
        "feed_url": "https://telegrafi.com/feed/",
        "language": FeedLanguage.ALBANIAN,
    },
    {
        "name": "Koha.net",
        "feed_url": "https://www.koha.net/feed/",
        "language": FeedLanguage.ALBANIAN,
    },
    {
        "name": "Portalb.mk",
        "feed_url": "https://portalb.mk/feed/",
        "language": FeedLanguage.ALBANIAN,
    },
    {
        "name": "Meta.mk",
        "feed_url": "https://meta.mk/feed/",
        "language": FeedLanguage.MACEDONIAN,
    },
    {
        "name": "Makfax",
        "feed_url": "https://makfax.com.mk/feed/",
        "language": FeedLanguage.MACEDONIAN,
    },
]


class Command(BaseCommand):
    help = "Krijon strukturën fillestare të faqeve dhe burimet RSS"

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-feeds",
            action="store_true",
            help="Mos shto burime RSS (vetëm krijo faqet)",
        )
        parser.add_argument(
            "--hostname",
            default="localhost",
            help="Hostname për Site (default: localhost)",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=80,
            help="Porta për Site (default: 80)",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO("\n=== HoW News - Setup Site ===\n"))

        home = self._ensure_home()
        self._ensure_news_index(home)
        self._ensure_gov_index(home)
        self._ensure_video_index(home)
        self._ensure_site(home, options["hostname"], options["port"])

        if not options["skip_feeds"]:
            self._add_feed_sources()

        self.stdout.write(self.style.SUCCESS(
            "\n[DONE] Setup kompletuar. Shko te http://localhost:8000/admin/ dhe logohu.\n"
        ))

    # ------------------------------------------------------------------
    # Faqet
    # ------------------------------------------------------------------

    def _ensure_home(self):
        existing = HomePage.objects.live().first()
        if existing:
            self.stdout.write(f"  [OK]HomePage ekziston: /{existing.slug}/")
            return existing

        root = Page.objects.filter(depth=1).first()
        home = HomePage(title="HoW News", slug="home", live=True)
        root.add_child(instance=home)
        self.stdout.write(self.style.SUCCESS("  [+]Krijova HomePage"))
        return home

    def _ensure_news_index(self, home):
        existing = NewsIndexPage.objects.first()
        if existing:
            if existing.get_parent().pk != home.pk:
                existing.move(home, pos="last-child")
                existing.refresh_from_db()
                self.stdout.write(self.style.SUCCESS(
                    "  [+]Levizja NewsIndexPage -> femijet e HomePage"
                ))
            if not existing.live:
                rev = existing.save_revision()
                rev.publish()
                self.stdout.write(self.style.SUCCESS("  [+]Publikova NewsIndexPage"))
            else:
                self.stdout.write(f"  [OK]NewsIndexPage: /{existing.slug}/")
            return existing

        page = NewsIndexPage(
            title="Lajme",
            slug="lajme",
            intro="",
        )
        home.add_child(instance=page)
        rev = page.save_revision()
        rev.publish()
        self.stdout.write(self.style.SUCCESS("  [+]Krijova dhe publikova NewsIndexPage (/lajme/)"))
        return page

    def _ensure_gov_index(self, home):
        existing = GovIndexPage.objects.first()
        if existing:
            self.stdout.write(f"  [OK]GovIndexPage ekziston: /{existing.slug}/")
            return existing

        page = GovIndexPage(
            title="Qeveria e Thjeshtë",
            slug="qeveria",
            intro="",
        )
        home.add_child(instance=page)
        rev = page.save_revision()
        rev.publish()
        self.stdout.write(self.style.SUCCESS("  [+]Krijova dhe publikova GovIndexPage (/qeveria/)"))
        return page

    def _ensure_video_index(self, home):
        existing = VideoIndexPage.objects.first()
        if existing:
            self.stdout.write(f"  [OK]VideoIndexPage ekziston: /{existing.slug}/")
            return existing

        page = VideoIndexPage(
            title="Video HoW",
            slug="video",
            intro="",
        )
        home.add_child(instance=page)
        rev = page.save_revision()
        rev.publish()
        self.stdout.write(self.style.SUCCESS("  [+]Krijova dhe publikova VideoIndexPage (/video/)"))
        return page

    # ------------------------------------------------------------------
    # Site
    # ------------------------------------------------------------------

    def _ensure_site(self, home, hostname, port):
        site = Site.objects.filter(is_default_site=True).first()
        if site:
            if site.root_page_id != home.pk:
                site.root_page = home
                site.hostname = hostname
                site.port = port
                site.save()
                self.stdout.write(self.style.SUCCESS(
                    f"  [+]Përditësova Site → {hostname}:{port} → HomePage"
                ))
            else:
                self.stdout.write(f"  [OK]Site: {site.hostname}:{site.port}")
        else:
            Site.objects.create(
                hostname=hostname,
                port=port,
                root_page=home,
                is_default_site=True,
                site_name="HoW News",
            )
            self.stdout.write(self.style.SUCCESS(f"  [+]Krijova Site {hostname}:{port}"))

    # ------------------------------------------------------------------
    # Burimet RSS
    # ------------------------------------------------------------------

    def _add_feed_sources(self):
        self.stdout.write("\n  Burimet RSS:")
        created = 0
        for feed_data in DEFAULT_FEEDS:
            obj, new = FeedSource.objects.get_or_create(
                feed_url=feed_data["feed_url"],
                defaults={
                    "name": feed_data["name"],
                    "language": feed_data["language"],
                    "is_active": True,
                },
            )
            if new:
                self.stdout.write(self.style.SUCCESS(
                    f"    [+]{obj.name} ({obj.get_language_display()})"
                ))
                created += 1
            else:
                self.stdout.write(f"    [OK]{obj.name} (ekziston)")

        if created:
            self.stdout.write(self.style.SUCCESS(
                f"\n  {created} burime të reja u shtuan. Ekzekuto:"
            ))
            self.stdout.write("    python manage.py fetch_feeds")
        else:
            self.stdout.write("  Të gjitha burimet ekzistojnë tashmë.")
