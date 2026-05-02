"""Pre-assign daily missions to bridge the gap between deploy and the cron's
first hourly tick. Mirrors adoorback/management/commands/preseed_daily_questions.py.

Respects the curated schedule: skips dates that already have a Mission scheduled.
"""
from __future__ import annotations

import datetime
import random

from django.core.management.base import BaseCommand

from mission.algorithms.data_crawler import NUM_DAILY_MISSIONS
from mission.models import Mission


class Command(BaseCommand):
    help = (
        "Pre-assign daily missions for N days starting from start_date. "
        "Skips dates already claimed by the curated study schedule."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "start_date",
            type=str,
            help="Date to start pre-seeding from (YYYY-MM-DD). The N days starting from this date are seeded.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Number of days to pre-seed (default: 7).",
        )
        parser.add_argument(
            "--per-day",
            type=int,
            default=NUM_DAILY_MISSIONS,
            help=f"Missions per day (default: {NUM_DAILY_MISSIONS}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview without making changes.",
        )

    def handle(self, *args, **options):
        try:
            start_date = datetime.date.fromisoformat(options["start_date"])
        except ValueError:
            self.stdout.write(self.style.ERROR("Invalid date format. Use YYYY-MM-DD."))
            return

        days = options["days"]
        per_day = options["per_day"]
        dry_run = options["dry_run"]

        all_dates = [start_date + datetime.timedelta(days=i) for i in range(days)]
        target_dates = [
            d for d in all_dates
            if not Mission.objects.filter(selected_dates__contains=[d]).exists()
        ]
        skipped = len(all_dates) - len(target_dates)

        total_needed = len(target_dates) * per_day
        if total_needed == 0:
            self.stdout.write(self.style.SUCCESS(
                f"All {len(all_dates)} dates already scheduled — nothing to do."
            ))
            return

        available = list(Mission.objects.filter(selected=False).values_list("id", flat=True))
        if len(available) < total_needed:
            self.stdout.write(self.style.WARNING(
                f"Only {len(available)} unselected missions, need {total_needed}. "
                f"Resetting selection flags on missions with empty selected_dates."
            ))
            if not dry_run:
                Mission.objects.filter(selected_dates=[]).update(selected=False)
            available = list(Mission.objects.filter(selected=False).values_list("id", flat=True))

        if len(available) < total_needed:
            self.stdout.write(self.style.ERROR(
                f"Not enough missions ({len(available)}) for {total_needed} slots "
                f"({len(target_dates)} days × {per_day}/day)."
            ))
            return

        random.shuffle(available)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"{'[DRY RUN] ' if dry_run else ''}"
            f"Pre-seeding {len(target_dates)} days × {per_day}/day = {total_needed} missions "
            f"({skipped} dates skipped — already scheduled)"
        ))

        idx = 0
        for date in target_dates:
            day_ids = available[idx:idx + per_day]
            idx += per_day
            missions = Mission.objects.filter(id__in=day_ids)
            for m in missions:
                if not dry_run:
                    m.selected_dates.append(date)
                    m.selected = True
                    m.save(update_fields=["selected_dates", "selected"])
                self.stdout.write(f"  {date}  M#{m.id}/{m.slug} — {m.prompt_en[:60]}")

        action = "Would assign" if dry_run else "Assigned"
        self.stdout.write(self.style.SUCCESS(
            f"\n{action} {total_needed} missions across {len(target_dates)} days."
        ))
