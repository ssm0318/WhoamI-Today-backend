from django.contrib.auth import get_user_model
from django.db.models import Q
from django.test import TestCase
from django.utils import timezone

from chat.models import ChatRoom, Message, OnboardingScreenshot
from chat.wit_bot import ensure_wit_bot_user

User = get_user_model()


class ScreenshotReviewSignalTests(TestCase):
    def setUp(self):
        # Operators with real emails (so wit_admin auto-provision succeeds for alice's signup)
        User.objects.create_user(
            username='jaewon', email='jaewonkim628@gmail.com', password='x',
        )
        User.objects.create_user(
            username='koyrkr', email='koyrkr@gmail.com', password='x',
        )
        User.objects.create_user(
            username='njs', email='njs03332@gmail.com', password='x',
        )
        self.alice = User.objects.create_user(
            username='alice', email='a@e.com', password='x',
        )
        self.bot = ensure_wit_bot_user()
        self.room = ChatRoom.objects.get(
            (Q(user1=self.alice) & Q(user2=self.bot))
            | (Q(user1=self.bot) & Q(user2=self.alice))
        )
        msg = Message.objects.create(
            chat_room=self.room, sender=self.alice, receiver=self.bot,
            content='widget upload',
        )
        self.shot = OnboardingScreenshot.objects.create(
            user=self.alice, version='version_w', kind='widget', message=msg,
        )

    def _bot_dms(self):
        return Message.objects.filter(chat_room=self.room, sender=self.bot)

    def test_approve_dms_participant(self):
        before = self._bot_dms().count()
        self.shot.status = 'approved'
        self.shot.reviewed_at = timezone.now()
        self.shot.save()
        self.assertGreater(self._bot_dms().count(), before)
        latest = self._bot_dms().order_by('-created_at').first()
        self.assertIn('confirmed', latest.content.lower())

    def test_reject_dms_participant_with_reason(self):
        self.shot.status = 'rejected'
        self.shot.rejection_reason = 'only 2 widgets visible'
        self.shot.reviewed_at = timezone.now()
        self.shot.save()
        latest = self._bot_dms().order_by('-created_at').first()
        self.assertIn('only 2 widgets visible', latest.content)
