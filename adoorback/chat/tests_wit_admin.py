from django.contrib.auth import get_user_model
from django.db.models import Q
from django.test import TestCase

from chat.models import ChatRoom, Message

User = get_user_model()


class WitAdminFieldsTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username='alice', email='alice@example.com', password='x')
        self.bob = User.objects.create_user(username='bob', email='bob@example.com', password='x')

    def test_chatroom_has_wit_admin_proxy_flag(self):
        room = ChatRoom.objects.create(user1=self.alice, user2=self.bob)
        self.assertFalse(room.is_wit_admin_proxy)

    def test_chatroom_has_blast_room_flag(self):
        room = ChatRoom.objects.create(user1=self.alice, user2=self.bob)
        self.assertFalse(room.is_wit_admin_blast_room)

    def test_message_has_mirror_flag(self):
        room = ChatRoom.objects.create(user1=self.alice, user2=self.bob)
        msg = Message.objects.create(chat_room=room, sender=self.alice, receiver=self.bob, content='hi')
        self.assertFalse(msg.is_wit_admin_mirror)


class WitAdminFlagsBackfillTests(TestCase):
    """Smoke check: after the backfill migration runs, every row must have False (not NULL)."""

    def test_all_chatrooms_have_non_null_flags(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        u1 = User.objects.create_user(username='u1', email='u1@example.com', password='x')
        u2 = User.objects.create_user(username='u2', email='u2@example.com', password='x')
        ChatRoom.objects.create(user1=u1, user2=u2)
        for room in ChatRoom.objects.all():
            self.assertIsNotNone(room.is_wit_admin_proxy)
            self.assertIsNotNone(room.is_wit_admin_blast_room)


class WitAdminFlagsNotNullTests(TestCase):
    def test_proxy_field_rejects_null(self):
        from django.db import IntegrityError
        from django.contrib.auth import get_user_model
        User = get_user_model()
        u1 = User.objects.create_user(username='nx1', email='nx1@example.com', password='x')
        u2 = User.objects.create_user(username='nx2', email='nx2@example.com', password='x')
        room = ChatRoom.objects.create(user1=u1, user2=u2)
        from django.db import connection
        with connection.cursor() as cur:
            with self.assertRaises(IntegrityError):
                cur.execute(
                    "UPDATE chat_chatroom SET is_wit_admin_proxy = NULL WHERE id = %s",
                    [room.id],
                )


class WitAdminHelpersTests(TestCase):
    def setUp(self):
        # Operators
        self.jaewon = User.objects.create_user(
            username='jaewon', email='jaewonkim628@gmail.com', password='x',
        )
        self.koyrkr = User.objects.create_user(
            username='koyrkr', email='koyrkr@gmail.com', password='x',
        )
        self.njs = User.objects.create_user(
            username='njs', email='njs03332@gmail.com', password='x',
        )
        # Regular users
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        self.bob = User.objects.create_user(username='b', email='b@e.com', password='x')

    def test_ensure_wit_admin_user_creates_inactive(self):
        from chat.wit_admin import ensure_wit_admin_user
        wit = ensure_wit_admin_user()
        self.assertEqual(wit.username, 'wit_admin')
        self.assertEqual(wit.email, 'whoami.today.official@gmail.com')
        self.assertFalse(wit.is_active)
        self.assertFalse(wit.has_usable_password())

    def test_ensure_wit_admin_user_idempotent(self):
        from chat.wit_admin import ensure_wit_admin_user
        a = ensure_wit_admin_user()
        b = ensure_wit_admin_user()
        self.assertEqual(a.id, b.id)

    def test_resolve_operators_returns_three(self):
        from chat.wit_admin import resolve_operators
        ops = resolve_operators()
        self.assertEqual({u.email for u in ops}, {
            'jaewonkim628@gmail.com', 'koyrkr@gmail.com', 'njs03332@gmail.com',
        })

    def test_resolve_operators_raises_on_missing(self):
        from chat.wit_admin import resolve_operators
        User.objects.filter(email='koyrkr@gmail.com').delete()
        with self.assertRaises(LookupError):
            resolve_operators()

    def test_provision_user_rooms_creates_four(self):
        from chat.wit_admin import provision_user_rooms, ensure_wit_admin_user
        ensure_wit_admin_user()
        provision_user_rooms(self.alice)
        # 1 wit_admin chat + 3 proxy rooms = 4
        wit_rooms = ChatRoom.objects.filter(
            Q(user1=self.alice) | Q(user2=self.alice)
        )
        self.assertEqual(wit_rooms.count(), 4)
        self.assertEqual(wit_rooms.filter(is_wit_admin_proxy=True).count(), 3)

    def test_provision_user_rooms_idempotent(self):
        from chat.wit_admin import provision_user_rooms, ensure_wit_admin_user
        ensure_wit_admin_user()
        provision_user_rooms(self.alice)
        provision_user_rooms(self.alice)
        wit_rooms = ChatRoom.objects.filter(Q(user1=self.alice) | Q(user2=self.alice))
        self.assertEqual(wit_rooms.count(), 4)

    def test_ensure_blast_rooms_creates_three(self):
        from chat.wit_admin import ensure_blast_rooms, ensure_wit_admin_user
        ensure_wit_admin_user()
        ensure_blast_rooms()
        self.assertEqual(ChatRoom.objects.filter(is_wit_admin_blast_room=True).count(), 3)

    def test_regular_recipients_excludes_operators_and_inactive(self):
        from chat.wit_admin import regular_recipients, ensure_wit_admin_user
        ensure_wit_admin_user()
        User.objects.create_user(username='dead', email='d@e.com', password='x', is_active=False)
        emails = {u.email for u in regular_recipients()}
        self.assertIn('a@e.com', emails)
        self.assertIn('b@e.com', emails)
        self.assertNotIn('jaewonkim628@gmail.com', emails)
        self.assertNotIn('koyrkr@gmail.com', emails)
        self.assertNotIn('njs03332@gmail.com', emails)
        self.assertNotIn('whoami.today.official@gmail.com', emails)
        self.assertNotIn('d@e.com', emails)
