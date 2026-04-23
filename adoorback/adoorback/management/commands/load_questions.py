from django.core.management.base import BaseCommand

from account.models import User
from qna.load_questions_tsv import bulk_create_questions_from_tsv, questions_tsv_path


class Command(BaseCommand):
    help = "Load questions from questions.tsv and create Question objects (admin author)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default=None,
            help="TSV file path (default: assets/questions.tsv under BASE_DIR).",
        )
        parser.add_argument(
            "--skip-duplicates",
            action="store_true",
            help="Skip rows whose (content_en, content_ko) already exists for this admin.",
        )

    def handle(self, *args, **options):
        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stdout.write(
                self.style.ERROR("No superuser found. Create a superuser first.")
            )
            return

        path = options.get("path")
        skip = options.get("skip_duplicates", False)
        count, status = bulk_create_questions_from_tsv(
            admin, path=path, skip_duplicates=skip
        )

        if status == "missing_file":
            self.stdout.write(
                self.style.ERROR(f"TSV not found: {questions_tsv_path(path)}")
            )
            return
        if status == "nothing_new":
            self.stdout.write(
                self.style.WARNING("No new questions to import (all duplicates or empty).")
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f"{count} questions successfully imported.")
        )
