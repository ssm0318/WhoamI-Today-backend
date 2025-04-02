import csv
from django.core.management.base import BaseCommand
from account.models import User


class Command(BaseCommand):
    help = "Update username_history field of users based on user_list.csv"

    def handle(self, *args, **options):
        input_file_path = 'adoorback/assets/user_list.csv'

        with open(input_file_path, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        updated_users = []
        skipped = []

        for row in rows:
            email = row.get('email', '').strip().lower()
            username_from_csv = row.get('username', '').strip()

            if not email or not username_from_csv:
                skipped.append((email or "(no email)", "missing email or username"))
                continue

            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                skipped.append((email, "User not found in DB"))
                continue

            # username_history가 None이면 빈 리스트로 초기화
            if user.username_history is None:
                user.username_history = []

            changed = False

            # 1. CSV에서 온 username 기록
            if username_from_csv not in user.username_history:
                user.username_history.append(username_from_csv)
                changed = True

            # 2. 현재 DB username이 다르면 그것도 기록
            if user.username != username_from_csv and user.username not in user.username_history:
                user.username_history.append(user.username)
                changed = True

            if changed:
                user.save()
                updated_users.append(user.email)

        self.stdout.write(self.style.SUCCESS(f'{len(updated_users)} users updated with new username_history.'))

        if skipped:
            print(f"\n⛔ Skipped {len(skipped)} rows:")
            for email, reason in skipped:
                print(f" - {email}: {reason}")
