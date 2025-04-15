import csv
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils.timezone import now

from account.models import User


class Command(BaseCommand):
    help = '(For Korean users) Automatically change the current_ver of user groups after 2 weeks.'

    def add_arguments(self, parser):
        parser.add_argument(
            'user_ids',
            nargs='*',
            type=int,
            help='Optional user IDs to update specifically',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting current version update...'))

        user_ids = options['user_ids']

        if user_ids:
            users = User.objects.filter(id__in=user_ids)
            self.stdout.write(f'Filtering by user IDs: {user_ids}')
        else:
            # Load email list from CSV
            csv_path = os.path.join(settings.BASE_DIR, 'assets', 'created_users.csv')
            with open(csv_path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                email_list = [row['email'].strip().lower() for row in reader if 'email' in row and row['email']]

            users = User.objects.filter(
                email__in=email_list,
                user_group__in=['group_3', 'group_4']
            )
            self.stdout.write(f'Filtering by emails from CSV: {len(users)} users found')

        # Check for users with mismatched user_group & current_ver values
        mismatched_users = users.filter(
            Q(user_group='group_1', current_ver='experiment') | 
            Q(user_group='group_2', current_ver='default') |
            Q(user_group='group_3', current_ver='experiment') |
            Q(user_group='group_4', current_ver='default')
        )

        if mismatched_users.exists():
            self.stdout.write(f'Mismatched users found: {mismatched_users.count()} users')
            self.stdout.write('Please fix these mismatches before running the command again.')
            return

        # group 1: default -> experiment
        updated_cnt = 0
        group_1_users = users.filter(user_group='group_1', current_ver='default')
        for user in group_1_users:
            user.current_ver = 'experiment'
            user.ver_changed_at = now()
            user.save()
            updated_cnt += 1

        self.stdout.write(f'Group 1 update complete: {updated_cnt} users')

        # group 2: experiment -> default
        updated_cnt = 0
        group_2_users = users.filter(user_group='group_2', current_ver='experiment')
        for user in group_2_users:
            user.current_ver = 'default'
            user.ver_changed_at = now()
            user.save()
            updated_cnt += 1

        self.stdout.write(f'Group 2 update complete: {updated_cnt} users')

        # group 3: default -> experiment
        updated_cnt = 0
        group_3_users = users.filter(user_group='group_3', current_ver='default')
        for user in group_3_users:
            user.current_ver = 'experiment'
            user.ver_changed_at = now()
            user.save()
            updated_cnt += 1

        self.stdout.write(f'Group 3 update complete: {updated_cnt} users')

        # group 4: experiment -> default
        updated_cnt = 0
        group_4_users = users.filter(user_group='group_4', current_ver='experiment')
        for user in group_4_users:
            user.current_ver = 'default'
            user.ver_changed_at = now()
            user.save()
            updated_cnt += 1

        self.stdout.write(f'Group 4 update complete: {updated_cnt} users')

        self.stdout.write(self.style.SUCCESS('All updates successfully completed!'))
