import datetime
import random

from django.core.management.base import BaseCommand

from qna.algorithms.data_crawler import NUM_DAILY_QUESTIONS
from qna.models import Question


class Command(BaseCommand):
    help = (
        "Pre-assign daily questions for the days leading up to experiment start. "
        "Sets selected_dates so users see questions from day one."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "start_date",
            type=str,
            help="Experiment start date (YYYY-MM-DD). Questions are seeded BEFORE this date.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Number of days before start_date to pre-seed (default: 7).",
        )
        parser.add_argument(
            "--per-day",
            type=int,
            default=NUM_DAILY_QUESTIONS,
            help=f"Questions per day (default: {NUM_DAILY_QUESTIONS}).",
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

        dates = [
            start_date - datetime.timedelta(days=i)
            for i in range(days, 0, -1)
        ]
        total_needed = days * per_day

        admin_qs = Question.objects.admin_questions_only()
        available = list(admin_qs.filter(selected=False).values_list("id", flat=True))

        if len(available) < total_needed:
            self.stdout.write(self.style.WARNING(
                f"Only {len(available)} unselected questions, need {total_needed}. "
                f"Resetting selection flags on all admin questions."
            ))
            if not dry_run:
                admin_qs.update(selected=False)
            available = list(admin_qs.values_list("id", flat=True))

        if len(available) < total_needed:
            self.stdout.write(self.style.ERROR(
                f"Not enough admin questions ({len(available)}) "
                f"for {total_needed} slots ({days} days × {per_day}/day)."
            ))
            return

        random.shuffle(available)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"{'[DRY RUN] ' if dry_run else ''}"
            f"Pre-seeding {days} days × {per_day}/day = {total_needed} questions"
        ))
        self.stdout.write(f"  Date range: {dates[0]} → {dates[-1]}\n")

        idx = 0
        for date in dates:
            day_ids = available[idx:idx + per_day]
            idx += per_day
            questions = Question.objects.filter(id__in=day_ids)

            for q in questions:
                if not dry_run:
                    q.selected_dates.append(date)
                    q.selected = True
                    q.save(update_fields=["selected_dates", "selected"])
                self.stdout.write(f"  {date}  Q#{q.id} — {q.content[:60]}")

        action = "Would assign" if dry_run else "Assigned"
        self.stdout.write(self.style.SUCCESS(
            f"\n{action} {total_needed} questions across {days} days."
        ))
