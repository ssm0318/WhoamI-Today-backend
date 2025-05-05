# account/management/commands/send_question_notification.py

from django.core.management.base import BaseCommand
from django.utils import timezone

from account.models import User
from notification.models import Notification, NotificationActor


class Command(BaseCommand):
    help = 'Send a research-related notification to all users.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('📣 Starting to send research notifications to all users...'))

        try:
            admin = User.objects.filter(is_superuser=True).get(email='whoami.today.official@gmail.com')
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR('❌ Admin user not found!'))
            return

        users = User.objects.all()
        count = 0

        for user in users:
            noti = Notification.objects.create(
                user=user,
                target=admin,
                origin=admin,
                message_ko="[📣 연구팀] Q&A 기능에서 여러분이 기대하는 점을 더 잘 이해할 수 있도록 도와주세요 🚀🚀",
                message_en="[📣 Research Team] Please help us understand what you’re hoping to get out of the Q&A feature 🚀🚀",
                redirect_url='/suggest-questions'
            )
            NotificationActor.objects.create(user=admin, notification=noti)
            count += 1

        self.stdout.write(self.style.SUCCESS(f'✅ {count} notifications successfully sent!'))
