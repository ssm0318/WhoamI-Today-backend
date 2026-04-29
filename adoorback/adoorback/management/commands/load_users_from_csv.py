import csv
from django.core.management.base import BaseCommand
from account.models import User
import os


class Command(BaseCommand):
    help = "Load users from a CSV and create new User instances"

    def handle(self, *args, **options):
        input_file_path = 'adoorback/assets/user_list.csv'
        output_file_path = 'adoorback/assets/created_users.csv'
        fixed_password = 'TempPass123!'

        with open(input_file_path, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)
            header = rows[0]
            data_rows = rows[1:]

            all_rows = [
                {
                    k: (
                        v.strip().lower() if k == 'email'
                        else v.strip()
                    )
                    for k, v in zip(header, row)
                }
                for row in data_rows
            ]

        print(f'{len(all_rows) = }')

        new_users = []
        skipped_details = []

        for row in all_rows:
            email = row.get('email', '')
            if not email:
                skipped_details.append(("(no email)", "missing or blank email"))
                print(f"⛔ (no email): missing or blank email")
                continue

            username = row.get('username', '').strip()
            if not username:
                skipped_details.append((email, "missing username"))
                print(f"⛔ {email}: missing username")
                continue

            if User.objects.filter(email=email).exists():
                skipped_details.append((email, "already exists in DB"))
                print(f"⛔ {email}: already exists in DB")
                continue

            user_group = row['user_group']
            current_ver = 'version_w' if user_group == 'group_w_first' else 'version_q'

            try:
                User.objects.create_user(
                    username=username,
                    email=email,
                    password=fixed_password,
                    user_group=user_group,
                    current_ver=current_ver,
                    language='en',
                    timezone='America/Los_Angeles',
                )
            except Exception as e:
                skipped_details.append((email, f"user creation failed: {str(e)}"))
                print(f"⛔ {email}: user creation failed: {str(e)}")
                continue

            new_users.append({'email': email, 'user_group': user_group})

        # Record created user information in CSV
        file_exists = os.path.exists(output_file_path)
        with open(output_file_path, 'a', newline='', encoding='utf-8') as outfile:
            writer = csv.writer(outfile)
            if not file_exists:
                writer.writerow(['email', 'user_group'])
            for user_info in new_users:
                writer.writerow([user_info['email'], user_info['user_group']])

        self.stdout.write(self.style.SUCCESS(f'{len(new_users)} new users created. Info saved to {output_file_path}.'))

        if skipped_details:
            print(f'\n⛔ 생성되지 않은 유저 {len(skipped_details)}명:')
            for email, reason in skipped_details:
                print(f' - {email}: {reason}')
        else:
            print('\n✅ 모든 유저가 성공적으로 생성되었습니다!')
