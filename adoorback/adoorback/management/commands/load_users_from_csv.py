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

            # ✅ 칼럼별 strip + lower 처리
            all_rows = [
                {
                    k: (
                        v.strip().lower() if k in ['email', 'friend-email']
                        else v.strip()
                    )
                    for k, v in zip(header, row)
                }
                for row in data_rows
            ]

        print(f'{len(all_rows) = }')

        email_to_row = {
            row['email']: row
            for row in all_rows if 'email' in row and row['email']
        }
        created_users = {}
        new_users = []
        skipped_details = []

        def create_user_by_email(email, skipped_details):
            if User.objects.filter(email=email).exists():
                reason = "already exists in DB"
                skipped_details.append((email, reason))
                print(f"⛔ {email}: {reason}")
                return None

            if email in created_users:
                return created_users[email]

            row = email_to_row.get(email)
            if not row:
                reason = "row not found in CSV"
                skipped_details.append((email, reason))
                print(f"⛔ {email}: {reason}")
                return None

            created_users[email] = None  # 생성 중 표시

            username = row.get('username', '').strip()
            if not username:
                reason = "missing username"
                skipped_details.append((email, reason))
                print(f"⛔ {email}: {reason}")
                return None

            user_group = f"group_{row['user_group']}"
            user_country = row['country']
            current_ver = 'default' if user_group in ['group_1', 'group_3'] else 'experiment'

            friend_email = row.get('friend-email', '')

            # 친구 먼저 생성 (자기 자신이 아닌 경우에만)
            if (
                friend_email and
                friend_email != email and
                friend_email in email_to_row and
                friend_email not in created_users
            ):
                create_user_by_email(friend_email, skipped_details)

            # friend_email 유효성 확인
            if friend_email == email:
                invited_from = None
                user_type = 'direct'
            elif friend_email in created_users and created_users[friend_email]:
                invited_from = created_users[friend_email]
                user_type = 'indirect'
            else:
                reason = f"friend-email {friend_email} is not created yet or invalid"
                skipped_details.append((email, reason))
                print(f"⛔ {email}: {reason}")
                return None

            try:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=fixed_password,
                    user_group=user_group,
                    current_ver=current_ver,
                    invited_from=invited_from,
                    user_type=user_type,
                    language=language,
                    timezone=timezone
                )
            except Exception as e:
                reason = f"user creation failed: {str(e)}"
                skipped_details.append((email, reason))
                print(f"⛔ {email}: {reason}")
                return None

            created_users[email] = user
            new_users.append({'email': email, 'user_group': user_group, 'country': user_country})
            return user

        # 전체 유저 생성 시도
        for row in all_rows:
            email = row.get('email', '')
            if not email:
                skipped_details.append(("(no email)", "missing or blank email"))
                print(f"⛔ (no email): missing or blank email")
                continue
            if email not in created_users and not User.objects.filter(email=email).exists():
                create_user_by_email(email, skipped_details)

        # CSV에 생성된 유저 정보 기록
        file_exists = os.path.exists(output_file_path)
        with open(output_file_path, 'a', newline='', encoding='utf-8') as outfile:
            writer = csv.writer(outfile)
            if not file_exists:
                writer.writerow(['email', 'user_group', 'country'])
            for user_info in new_users:
                writer.writerow([user_info['email'], user_info['user_group'], user_info['country']])

        self.stdout.write(self.style.SUCCESS(f'{len(new_users)} new users created. Info saved to {output_file_path}.'))

        # ✅ 최종적으로 생성되지 않은 유저만 출력
        permanently_skipped = [
            (email, reason)
            for (email, reason) in skipped_details
            if created_users.get(email) is None
        ]

        if permanently_skipped:
            print(f'\n⛔ 생성되지 않은 유저 {len(permanently_skipped)}명:')
            for email, reason in permanently_skipped:
                print(f' - {email}: {reason}')
        else:
            print('\n✅ 모든 유저가 성공적으로 생성되었습니다!')
