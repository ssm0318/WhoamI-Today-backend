import csv
from django.core.management.base import BaseCommand
from account.models import User, Connection
import os


class Command(BaseCommand):
    help = "Load users from a CSV and create new User instances"

    def handle(self, *args, **options):
        file_paths = {
            'us': 'adoorback/assets/user_list_us.csv',
            'ko': 'adoorback/assets/user_list_ko.csv'
        }
        output_file_path = 'adoorback/assets/created_users.csv'

        country_aliases = {
            'us': ['미국', 'US'],
            'ko': ['한국', 'Korea']
        }

        group_map = {
            'us': ['group_1', 'group_2'],
            'ko': ['group_3', 'group_4']
        }
        default_groups = ['group_1', 'group_3']
        fixed_password = 'TempPass123!'

        all_rows = []
        for file_country, file_path in file_paths.items():
            with open(file_path, mode='r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                rows = list(reader)
                header = rows[0]
                data_rows = rows[3:]
                dict_rows = [dict(zip(header, row)) for row in data_rows]
                for row in dict_rows:
                    row['file_country'] = file_country
                all_rows.extend(dict_rows)

        print(f'{len(all_rows) = }')

        email_to_row = {
            row['email'].strip().lower(): row
            for row in all_rows if 'email' in row and row['email'].strip()
        }
        created_users = {}
        new_users = []
        skipped_details = []

        group_counts = {
            group: User.objects.filter(user_group=group).count()
            for groups in group_map.values() for group in groups
        }

        def get_country(row):
            value = row.get('country', '').strip()
            if value:
                if value in country_aliases['ko']:
                    return 'ko'
                elif value in country_aliases['us']:
                    return 'us'
            return row.get('file_country')

        def create_user_by_email(email, skipped_details):
            email = email.lower()
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

            created_users[email] = None

            user_country = get_country(row)
            g1, g2 = group_map[user_country]

            friend_email = row.get('friend-email')
            if friend_email == email:
                friend_email = None

            if friend_email and friend_email in email_to_row and friend_email not in created_users:
                create_user_by_email(friend_email, skipped_details)

            if friend_email and friend_email in created_users and created_users[friend_email]:
                friend_user = created_users[friend_email]
                user_group = friend_user.user_group
                current_ver = friend_user.current_ver
                invited_from = friend_user
                user_type = 'indirect'
            else:
                user_group = g1 if group_counts[g1] <= group_counts[g2] else g2
                group_counts[user_group] += 1
                current_ver = 'default' if user_group in default_groups else 'experiment'
                invited_from = None
                user_type = 'direct'

            try:
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=fixed_password,
                    user_group=user_group,
                    current_ver=current_ver,
                    invited_from=invited_from,
                    user_type=user_type
                )
            except Exception as e:
                reason = f"user creation failed: {str(e)}"
                skipped_details.append((email, reason))
                print(f"⛔ {email}: {reason}")
                return None

            if user_group == 'group_1':
                whoami_user = User.objects.get(username='whoami_today_r_us')
            elif user_group == 'group_2':
                whoami_user = User.objects.get(username='whoami_today_q_us')
            elif user_group == 'group_3':
                whoami_user = User.objects.get(username='whoami_today_r_ko')
            elif user_group == 'group_4':
                whoami_user = User.objects.get(username='whoami_today_q_ko')
            else:
                whoami_user = None

            if whoami_user:
                try:
                    Connection.objects.create(
                        user1=user,
                        user2=whoami_user,
                        user1_choice='friend',
                        user2_choice='friend',
                    )
                except Exception as e:
                    print(f"⚠️ Connection failed for {email}: {str(e)}")

            created_users[email] = user
            new_users.append({'email': email, 'user_group': user_group, 'country': user_country})
            return user

        for row in all_rows:
            raw_email = row.get('email', '').strip()
            if not raw_email:
                skipped_details.append(("(no email)", "missing or blank email"))
                print(f"⛔ (no email): missing or blank email")
                continue
            email = raw_email.strip().lower()
            if email not in created_users and not User.objects.filter(email=email).exists():
                create_user_by_email(email, skipped_details)

        file_exists = os.path.exists(output_file_path)
        with open(output_file_path, 'a', newline='', encoding='utf-8') as outfile:
            writer = csv.writer(outfile)
            if not file_exists:
                writer.writerow(['email', 'user_group', 'country'])
            for user_info in new_users:
                writer.writerow([user_info['email'], user_info['user_group'], user_info['country']])

        self.stdout.write(self.style.SUCCESS(f'{len(new_users)} new users created. Info saved to {output_file_path}.'))

        if skipped_details:
            print(f'\n⛔ 생성되지 않은 유저 {len(skipped_details)}명:')
            for email, reason in skipped_details:
                print(f' - {email}: {reason}')
        else:
            print('\n✅ 모든 유저가 성공적으로 생성되었습니다!')
