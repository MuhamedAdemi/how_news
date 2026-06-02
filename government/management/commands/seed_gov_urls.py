"""
Management command: python manage.py seed_gov_urls

Proceson nje liste URL-sh te kuruar manualisht nga portalet qeveritare te RMV.
Perdor AI (Groq/LLaMA) per te thjeshtesuar dhe perkthyer cdo faqe ne Shqip.

Perdorim:
    python manage.py seed_gov_urls          # proceson te gjitha URL-t e reja
    python manage.py seed_gov_urls --dry    # shfaq listen pa procesuar
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand

from government.models import GovItemPage

# URL-t me te rendesishme qeveritare — kuruar manualisht
# Shto URL te reja ketu kur i gjen
SEED_URLS = [
    # ----------------------------------------------------------------
    # Vlada.mk — Qeveria Qendrore
    # ----------------------------------------------------------------
    "https://vlada.mk/mk-MK/vlada/sednici-na-vlada",
    "https://vlada.mk/mk-MK/odnosi-so-javnost/soopstuvanja-od-sednici",
    "https://vlada.mk/mk-MK/ekonomija/fondovi-i-proekti",

    # ----------------------------------------------------------------
    # Portalb.mk — Lajme Shqip per RMV (me RSS + me permbajtje te mire)
    # ----------------------------------------------------------------
    "https://portalb.mk/category/ekonomi/",
    "https://portalb.mk/category/shoqeri/",
    "https://portalb.mk/category/politike/",

    # ----------------------------------------------------------------
    # Ministria e Finances
    # ----------------------------------------------------------------
    "https://finance.gov.mk/mk/category/budzet/",
    "https://finance.gov.mk/mk/category/javni-pobaruvanja/",

    # ----------------------------------------------------------------
    # MTSP — Ministria e Punes dhe Politikes Sociale
    # ----------------------------------------------------------------
    "https://mtsp.gov.mk/content/xml/mk/zakonodavstvo/zakoni.xml",
    "https://mtsp.gov.mk/mk/",

    # ----------------------------------------------------------------
    # e-Nabavki — Tenderat Publike (HTML, jo SPA)
    # ----------------------------------------------------------------
    "https://e-nabavki.gov.mk/PublicAccess/home.aspx#/dossie-activies/1",

    # ----------------------------------------------------------------
    # UJP — Drejtoria e te Ardhurave Publike (Tatimi)
    # ----------------------------------------------------------------
    "https://ujp.gov.mk/mk/",
    "https://ujp.gov.mk/mk/pocetna/vesti",

    # ----------------------------------------------------------------
    # Bashkite lokale kryesore (me popullate shqiptare)
    # ----------------------------------------------------------------
    "https://tetovo.gov.mk/",
    "https://gostivar.gov.mk/",
    "https://debar.gov.mk/",
]


class Command(BaseCommand):
    help = "Proceson liste URL-sh te kuratura qeveritare me AI"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry",
            action="store_true",
            help="Shfaq listen pa procesuar",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            default=True,
            help="Kalo URL-t qe ekzistojne tashme (default: True)",
        )

    def handle(self, *args, **options):
        if options["dry"]:
            self.stdout.write(f"\n{len(SEED_URLS)} URL ne liste:\n")
            for url in SEED_URLS:
                exists = GovItemPage.objects.filter(source_url=url).exists()
                status = "[ekziston]" if exists else "[e re]    "
                self.stdout.write(f"  {status}  {url}")
            return

        self.stdout.write(self.style.HTTP_INFO(
            f"\n=== seed_gov_urls: {len(SEED_URLS)} URL ===\n"
        ))

        processed = 0
        skipped = 0

        for url in SEED_URLS:
            if GovItemPage.objects.filter(source_url=url).exists():
                self.stdout.write(f"  [skip] {url[:70]}")
                skipped += 1
                continue

            self.stdout.write(f"\n  [>>] {url[:70]}")
            try:
                call_command("process_url", url, verbosity=0)
                processed += 1
            except SystemExit:
                pass
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"       [ERR] {exc}"))

        self.stdout.write(self.style.SUCCESS(
            f"\n[DONE] {processed} te reja, {skipped} skip.\n"
            f"Per teshtuar URL te reja, edito:\n"
            f"  government/management/commands/seed_gov_urls.py"
        ))
