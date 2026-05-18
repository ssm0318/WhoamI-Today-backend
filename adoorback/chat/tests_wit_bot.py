from django.contrib.auth import get_user_model
from django.db.models import Q
from django.test import TestCase

from chat.models import ChatRoom

User = get_user_model()


class WitBotHelpersTests(TestCase):
    def setUp(self):
        # Operators (must exist for the new-signup signal to provision rooms).
        self.jaewon = User.objects.create_user(
            username='jaewon', email='jaewonkim628@gmail.com', password='x',
        )
        self.koyrkr = User.objects.create_user(
            username='koyrkr', email='koyrkr@gmail.com', password='x',
        )
        self.njs = User.objects.create_user(
            username='njs', email='njs03332@gmail.com', password='x',
        )

    def test_ensure_wit_bot_user_creates_with_canonical_identity(self):
        from chat.wit_bot import ensure_wit_bot_user, WIT_BOT_USERNAME, WIT_BOT_EMAIL
        bot = ensure_wit_bot_user()
        self.assertEqual(bot.username, WIT_BOT_USERNAME)
        self.assertEqual(bot.email, WIT_BOT_EMAIL)

    def test_ensure_wit_bot_user_idempotent(self):
        from chat.wit_bot import ensure_wit_bot_user
        a = ensure_wit_bot_user()
        b = ensure_wit_bot_user()
        self.assertEqual(a.id, b.id)

    def test_ensure_wit_bot_user_preserves_manual_auth_state(self):
        from chat.wit_bot import ensure_wit_bot_user
        bot = ensure_wit_bot_user()
        bot.set_password('manual')
        bot.is_active = False
        bot.save()
        bot2 = ensure_wit_bot_user()
        self.assertFalse(bot2.is_active)
        self.assertTrue(bot2.check_password('manual'))

    def test_is_wit_bot_helper(self):
        from chat.wit_bot import ensure_wit_bot_user, is_wit_bot
        bot = ensure_wit_bot_user()
        self.assertTrue(is_wit_bot(bot))
        self.assertFalse(is_wit_bot(self.jaewon))
        self.assertFalse(is_wit_bot(None))

    def test_ensure_wit_bot_room_creates_one_room(self):
        from chat.wit_bot import ensure_wit_bot_room, ensure_wit_bot_user
        alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        bot = ensure_wit_bot_user()
        room = ensure_wit_bot_room(alice)
        self.assertIsNotNone(room)
        # The room is a plain 1-on-1 with no wit_admin proxy/blast flags.
        self.assertFalse(room.is_group)
        self.assertFalse(room.is_wit_admin_proxy)
        self.assertFalse(room.is_wit_admin_blast_room)
        self.assertEqual(set(filter(None, [room.user1_id, room.user2_id])), {alice.id, bot.id})

    def test_ensure_wit_bot_room_idempotent(self):
        from chat.wit_bot import ensure_wit_bot_room, ensure_wit_bot_user
        alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        bot = ensure_wit_bot_user()
        ensure_wit_bot_room(alice)
        ensure_wit_bot_room(alice)
        rooms = ChatRoom.objects.filter(
            (Q(user1=alice) & Q(user2=bot)) | (Q(user1=bot) & Q(user2=alice))
        )
        self.assertEqual(rooms.count(), 1)

    def test_ensure_wit_bot_room_skips_system_users(self):
        from chat.wit_bot import ensure_wit_bot_room, ensure_wit_bot_user
        from chat.wit_admin import ensure_wit_admin_user
        bot = ensure_wit_bot_user()
        admin = ensure_wit_admin_user()
        # Each system user passes through ensure_wit_bot_room → no-op.
        for u in (bot, admin, self.jaewon, self.koyrkr, self.njs):
            self.assertIsNone(ensure_wit_bot_room(u))


class WitBotAutoSignupProvisioningTests(TestCase):
    def setUp(self):
        # Operators must exist so wit_admin signal succeeds.
        User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')

    def test_new_user_gets_wit_bot_room_automatically(self):
        from chat.wit_bot import WIT_BOT_USERNAME
        new_user = User.objects.create_user(username='new', email='new@e.com', password='x')
        wit_bot_rooms = ChatRoom.objects.filter(
            (Q(user1=new_user) & Q(user2__username=WIT_BOT_USERNAME))
            | (Q(user2=new_user) & Q(user1__username=WIT_BOT_USERNAME))
        )
        self.assertEqual(wit_bot_rooms.count(), 1)

    def test_operator_signup_does_not_get_wit_bot_room(self):
        # All 3 operators were created in setUp; none should have wit_bot rooms.
        from chat.wit_bot import WIT_BOT_USERNAME
        bot_rooms = ChatRoom.objects.filter(
            Q(user1__username=WIT_BOT_USERNAME) | Q(user2__username=WIT_BOT_USERNAME)
        )
        self.assertEqual(bot_rooms.count(), 0)


class SeedWitBotCommandTests(TestCase):
    def setUp(self):
        User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        self.bob = User.objects.create_user(username='bob', email='b@e.com', password='x')

    def test_command_creates_wit_bot_user_and_rooms(self):
        from django.core.management import call_command
        from chat.wit_bot import WIT_BOT_USERNAME
        # Prevent the auto-provisioning signal from racing the test by deleting
        # any wit_bot↔user rooms first.
        ChatRoom.objects.filter(
            Q(user1__username=WIT_BOT_USERNAME) | Q(user2__username=WIT_BOT_USERNAME)
        ).delete()
        call_command('seed_wit_bot')
        # 2 regular users → 2 wit_bot 1-on-1 rooms.
        bot_rooms = ChatRoom.objects.filter(
            Q(user1__username=WIT_BOT_USERNAME) | Q(user2__username=WIT_BOT_USERNAME)
        )
        self.assertEqual(bot_rooms.count(), 2)
        self.assertTrue(User.objects.filter(username=WIT_BOT_USERNAME).exists())

    def test_command_idempotent(self):
        from django.core.management import call_command
        call_command('seed_wit_bot')
        first = ChatRoom.objects.count()
        call_command('seed_wit_bot')
        self.assertEqual(ChatRoom.objects.count(), first)


class WitBotFastPathTests(TestCase):
    """The wit_bot fast path on POST /chat/user/<bot_id>/ should:
    - skip notification creation (bot is reactive; user is in-app)
    - skip WS broadcast (bot reply rides back inline)
    - return bot replies in `bot_replies` on the response
    """

    def setUp(self):
        # Operators required for signup signal.
        User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        from chat.wit_bot import ensure_wit_bot_user
        self.bot = ensure_wit_bot_user()

    def test_bot_reply_does_not_create_notification(self):
        from chat.models import Message
        from notification.models import Notification
        from django.contrib.contenttypes.models import ContentType
        msg_ct = ContentType.objects.get_for_model(Message)
        before = Notification.objects.filter(user=self.alice, target_type=msg_ct).count()
        # Trigger a turn: alice sends a non-admin button payload.
        from rest_framework.test import APIRequestFactory, force_authenticate
        from chat.views import MessageList
        factory = APIRequestFactory()
        req = factory.post(
            f'/api/chat/user/{self.bot.id}/',
            {'emoji': '', 'content': 'tehehe',
             'bot_payload': {'kind': 'choice', 'payload': 'tehehe'}},
            format='json',
        )
        force_authenticate(req, user=self.alice)
        resp = MessageList.as_view()(req, pk=self.bot.id)
        self.assertEqual(resp.status_code, 201)
        after = Notification.objects.filter(user=self.alice, target_type=msg_ct).count()
        self.assertEqual(before, after, 'bot replies must not create chat notifications')

    def test_bot_reply_returned_inline(self):
        """Engine still posts replies inline. With the new intent dispatch,
        an unrecognized payload from idle yields the idle nudge. The welcome
        card is state chrome, not a conversational reply, so it must not ride
        back in bot_replies."""
        from rest_framework.test import APIRequestFactory, force_authenticate
        from chat.views import MessageList
        factory = APIRequestFactory()
        req = factory.post(
            f'/api/chat/user/{self.bot.id}/',
            {'emoji': '', 'content': 'tehehe',
             'bot_payload': {'kind': 'choice', 'payload': 'tehehe'}},
            format='json',
        )
        force_authenticate(req, user=self.alice)
        resp = MessageList.as_view()(req, pk=self.bot.id)
        self.assertEqual(resp.status_code, 201)
        bot_replies = resp.data.get('bot_replies') or []
        self.assertFalse(any(r.get('event_type') == 'wit_welcome_card' for r in bot_replies))
        self.assertEqual(len(bot_replies), 1)
        self.assertEqual(bot_replies[0]['sender']['username'], 'wit_bot')
        # Idle handler posts a short nudge — no card.
        self.assertIn('not sure', bot_replies[0]['content'].lower())
