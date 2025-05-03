from django.core.management.base import BaseCommand
from account.models import User

class Command(BaseCommand):
    help = 'Automatically change the current_ver of all users to experiment.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting current version update...'))

        updated_cnt = User.objects.filter(current_ver='default').update(current_ver='experiment')
        total_users = User.objects.count()

        self.stdout.write(f'Update complete: {updated_cnt} users out of {total_users} users.')
        self.stdout.write(self.style.SUCCESS('All updates successfully completed!'))
