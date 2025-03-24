import csv
import random
import string
from django.core.management.base import BaseCommand
from account.models import User, Connection
import os


class Command(BaseCommand):
    help = "Load users from a CSV and create new User instances"

    def add_arguments(self, parser):
        parser.add_argument('country', type=str, choices=['us', 'ko'], help="Country code: 'us' or 'ko'")

    def handle(self, *args, **options):
        country = options['country']
        file_path = f"adoorback/assets/user_list_{country}.csv"
        password_file_path = f"adoorback/assets/passwords_{country}.csv"

        group_map = {
            'us': ['group_1', 'group_2'],
            'ko': ['group_3', 'group_4']
        }
        default_groups = ['group_1', 'group_3']

        with open(file_path, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)

        header = rows[0]
        data_rows = rows[3:]
        dict_rows = [dict(zip(header, row)) for row in data_rows]

        email_to_row = {row['email']: row for row in dict_rows if 'email' in row}
        created_users = {}
        new_users = []

        group_counts = {group: User.objects.filter(user_group=group).count() for group in group_map[country]}

        whoami_r = User.objects.get(username='whoami_today_r')
        whoami_q = User.objects.get(username='whoami_today_q')

        def create_user_by_email(email):
            email = email.lower()
            if User.objects.filter(email=email).exists():
                return None

            if email in created_users:
                return created_users[email]

            row = email_to_row.get(email)
            if not row or User.objects.filter(email=email).exists():
                return None

            friend_email = row.get('friend-email')
            if friend_email == email:
                friend_email = None

            if friend_email and friend_email in email_to_row and friend_email not in created_users:
                create_user_by_email(friend_email)

            password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))

            if friend_email and friend_email in created_users:
                friend_user = created_users[friend_email]
                user_group = friend_user.user_group
                current_ver = friend_user.current_ver
                invited_from = friend_user
                user_type = 'indirect'
            else:
                g1, g2 = group_map[country]
                user_group = g1 if group_counts[g1] <= group_counts[g2] else g2
                group_counts[user_group] += 1
                current_ver = 'default' if user_group in default_groups else 'experiment'
                invited_from = None
                user_type = 'direct'

            user = User.objects.create_user(
                username=email.lower(),
                email=email.lower(),
                password=password,
                user_group=user_group,
                current_ver=current_ver,
                invited_from=invited_from,
                user_type=user_type
            )

            # 이메일-비밀번호 기록
            with open(password_file_path, 'a', newline='', encoding='utf-8') as pwfile:
                writer = csv.writer(pwfile)
                if os.stat(password_file_path).st_size == 0:
                    writer.writerow(['email', 'password', 'user_group'])
                writer.writerow([email.lower(), password, user_group])

            # 👥 친구 연결
            if current_ver == 'default':
                Connection.objects.create(
                    user1=user,
                    user2=whoami_r,
                    user1_choice='friend',
                    user2_choice='friend',
                )
            elif current_ver == 'experiment':
                Connection.objects.create(
                    user1=user,
                    user2=whoami_q,
                    user1_choice='friend',
                    user2_choice='friend',
                )

            created_users[email] = user
            new_users.append(row)
            return user

        for row in dict_rows:
            email = row.get('email')
            if email and email not in created_users and not User.objects.filter(email=email).exists():
                create_user_by_email(email)

        self.stdout.write(self.style.SUCCESS(f'{len(new_users)} new users created. Passwords saved to {password_file_path}.'))
