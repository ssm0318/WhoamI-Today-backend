from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils.timezone import now

from account.models import User


class Command(BaseCommand):
    help = '(For Korean users) Automatically change the current_ver of user groups after 2 weeks.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('Starting current version update...'))

        # Check for users with mismatched user_group & current_ver values
        mismatched_users = User.objects.filter(
            Q(user_group='group_3', current_ver='experiment') | 
            Q(user_group='group_4', current_ver='default')
        )

        if mismatched_users.exists():
            self.stdout.write(f'Mismatched users found: {mismatched_users.count()} users')
            self.stdout.write('Please fix these mismatches before running the command again.')
            return

        # group 3: default -> experiment
        group_3_users = User.objects.filter(user_group='group_3', current_ver='default')
        for user in group_3_users:
            user.current_ver = 'experiment'
            user.ver_changed_at = now()
            user.save()

        self.stdout.write(f'Group 3 update complete: {group_3_users.count()} users')

        # group 4: experiment -> default
        group_4_users = User.objects.filter(user_group='group_4', current_ver='experiment')
        for user in group_4_users:
            user.current_ver = 'default'
            user.ver_changed_at = now()
            user.save()

        self.stdout.write(f'Group 2 update complete: {group_4_users.count()} users')

        self.stdout.write(self.style.SUCCESS('All updates successfully completed!'))
