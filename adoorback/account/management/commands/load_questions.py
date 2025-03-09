import csv

from django.core.management.base import BaseCommand

from account.models import User
from qna.models import Question


class Command(BaseCommand):
    help = "Load questions from a TSV file and create Question objects"

    def handle(self, *args, **kwargs):
        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stdout.write(self.style.ERROR("No superuser found. Create a superuser first."))
            return

        file_path = "adoorback/assets/questions.tsv"

        questions = []
        with open(file_path, newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file, delimiter='\t')
            for row in reader:
                question = Question(
                    author=admin,
                    is_admin_question=True,
                    content_en=row["content_en"],
                    content_ko=row["content_ko"]
                )
                questions.append(question)

        Question.objects.bulk_create(questions)
        self.stdout.write(self.style.SUCCESS(f"{len(questions)} questions successfully imported."))
