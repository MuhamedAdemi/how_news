"""
Management command: python manage.py expire_gov_items

Shënon si të skaduara të gjitha GovItemPage me deadline të kaluar.
Mundësisht i fsheh nga faqja publike (unpublish).

Perdorim:
    python manage.py expire_gov_items              # skadoj + unpublish
    python manage.py expire_gov_items --dry        # shfaq pa ndryshuar
    python manage.py expire_gov_items --keep-live  # skadoj por mos unpublish
    python manage.py expire_gov_items --purge-days 90  # fshi te skaduarat >90 dite
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from government.models import GovItemPage, GovItemStatus


class Command(BaseCommand):
    help = "Skadoj GovItemPage me deadline te kaluar"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry",
            action="store_true",
            help="Shfaq pa ndryshuar asgje",
        )
        parser.add_argument(
            "--keep-live",
            action="store_true",
            help="Sheno si expired por mos i unpublish",
        )
        parser.add_argument(
            "--purge-days",
            type=int,
            default=0,
            help="Fshi pergjithmone items me deadline > N dite me pare (0 = mos fshi)",
        )

    def handle(self, *args, **options):
        dry = options["dry"]
        keep_live = options["keep_live"]
        purge_days = options["purge_days"]
        today = timezone.now().date()

        self.stdout.write(self.style.HTTP_INFO(
            f"\n=== expire_gov_items ===\n"
            f"    Sot: {today} | Dry: {dry} | Keep-live: {keep_live}\n"
        ))

        # ── 1. Gjej items me deadline te kaluar dhe akoma aktive ─────────
        to_expire = GovItemPage.objects.live().filter(
            deadline__lt=today,
            status__in=[GovItemStatus.ACTIVE, GovItemStatus.UPCOMING],
        )

        expired_count = 0
        for item in to_expire:
            days_ago = (today - item.deadline).days
            self.stdout.write(
                f"  [SKADUAR {days_ago}d] {item.title[:70]}\n"
                f"           Afati: {item.deadline} | Domain: {item.domain}"
            )

            if not dry:
                item.status = GovItemStatus.EXPIRED
                item.save(update_fields=["status"])

                if not keep_live:
                    item.unpublish()

            expired_count += 1

        if expired_count == 0:
            self.stdout.write(self.style.SUCCESS("    Nuk ka items te skaduar. Gjithcka eshte aktuale."))
        elif not dry:
            self.stdout.write(self.style.SUCCESS(
                f"\n  [OK] {expired_count} items te shenuar si EXPIRED"
                + (" (te fshehur nga faqja)" if not keep_live else " (te dukshme ende)")
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"\n  [DRY] {expired_count} items do te skadonin."
            ))

        # ── 2. Fshi pergjithmone shume te vjetrat (opsionale) ────────────
        if purge_days > 0:
            cutoff = today - timedelta(days=purge_days)
            old_items = GovItemPage.objects.filter(
                status=GovItemStatus.EXPIRED,
                deadline__lt=cutoff,
            )
            purge_count = old_items.count()

            if purge_count:
                self.stdout.write(self.style.WARNING(
                    f"\n  [PURGE] Gjeta {purge_count} items me deadline para {cutoff}"
                ))
                if not dry:
                    for item in old_items:
                        self.stdout.write(f"    [DEL] {item.title[:60]}")
                        item.delete()
                    self.stdout.write(self.style.SUCCESS(f"  [OK] {purge_count} items te fshire."))
                else:
                    self.stdout.write(self.style.WARNING(f"  [DRY] {purge_count} items do te fshiheshin."))
            else:
                self.stdout.write(f"    Nuk ka items per purge (>{purge_days} dite).")

        # ── 3. Statistikat ───────────────────────────────────────────────
        total_active = GovItemPage.objects.live().filter(status=GovItemStatus.ACTIVE).count()
        total_expired = GovItemPage.objects.filter(status=GovItemStatus.EXPIRED).count()
        no_deadline = GovItemPage.objects.live().filter(
            status=GovItemStatus.ACTIVE, deadline__isnull=True
        ).count()

        self.stdout.write(self.style.HTTP_INFO(
            f"\n  Statistikat:\n"
            f"    Aktive:          {total_active}\n"
            f"    Pa afat (aktive): {no_deadline}\n"
            f"    Te skaduara:     {total_expired}\n"
        ))
