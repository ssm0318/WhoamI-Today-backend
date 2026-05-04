from django.contrib.auth import get_user_model
from django.test import TestCase

from chat.models import ChatRoom, Message, OnboardingScreenshot

User = get_user_model()


class OnboardingScreenshotModelTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            username='alice', email='a@e.com', password='x',
        )
        self.bot = User.objects.create_user(
            username='wit_bot', email='b@e.com', password='x',
        )
        self.room = ChatRoom.objects.create(user1=self.alice, user2=self.bot)
        self.msg = Message.objects.create(
            chat_room=self.room, sender=self.alice, receiver=self.bot,
            content='screenshot upload', bot_payload={'kind': 'choice', 'payload': 'screenshot'},
        )

    def test_create_pending_screenshot(self):
        shot = OnboardingScreenshot.objects.create(
            user=self.alice, version='version_w', kind='widget', message=self.msg,
        )
        self.assertEqual(shot.status, 'pending')
        self.assertEqual(shot.kind, 'widget')
        self.assertEqual(shot.version, 'version_w')
        self.assertIsNone(shot.reviewed_by)
        self.assertIsNone(shot.reviewed_at)

    def test_str_representation(self):
        shot = OnboardingScreenshot.objects.create(
            user=self.alice, version='version_w', kind='widget', message=self.msg,
        )
        self.assertIn('alice', str(shot))
        self.assertIn('widget', str(shot))
        self.assertIn('pending', str(shot))
