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
        self.assertEqual(wit.email, 'zeoni.res@gmail.com')
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
        self.assertNotIn('zeoni.res@gmail.com', emails)
        self.assertNotIn('d@e.com', emails)


class SeedWitAdminChatsCommandTests(TestCase):
    def setUp(self):
        self.jaewon = User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        self.koyrkr = User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        self.njs = User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        self.bob = User.objects.create_user(username='bob', email='b@e.com', password='x')

    def test_command_creates_expected_rooms(self):
        from django.core.management import call_command
        call_command('seed_wit_admin_chats')
        # 2 regular users * (1 wit_admin + 3 proxy) = 8, plus 3 blast rooms = 11
        self.assertEqual(ChatRoom.objects.count(), 11)
        self.assertEqual(ChatRoom.objects.filter(is_wit_admin_proxy=True).count(), 6)
        self.assertEqual(ChatRoom.objects.filter(is_wit_admin_blast_room=True).count(), 3)

    def test_command_is_idempotent(self):
        from django.core.management import call_command
        call_command('seed_wit_admin_chats')
        first = ChatRoom.objects.count()
        call_command('seed_wit_admin_chats')
        self.assertEqual(ChatRoom.objects.count(), first)

    def test_command_aborts_when_operator_missing(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        self.koyrkr.delete()
        with self.assertRaises(CommandError):
            call_command('seed_wit_admin_chats')


class AutoSignupProvisioningTests(TestCase):
    def setUp(self):
        # Pre-create operators so resolve_operators() succeeds
        User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        from chat.wit_admin import ensure_wit_admin_user, ensure_blast_rooms
        ensure_wit_admin_user()
        ensure_blast_rooms()

    def test_new_user_gets_four_rooms_automatically(self):
        new_user = User.objects.create_user(username='new', email='new@e.com', password='x')
        rooms = ChatRoom.objects.filter(Q(user1=new_user) | Q(user2=new_user))
        self.assertEqual(rooms.count(), 4)
        self.assertEqual(rooms.filter(is_wit_admin_proxy=True).count(), 3)

    def test_inactive_new_user_skipped(self):
        new_user = User.objects.create_user(
            username='nope', email='nope@e.com', password='x', is_active=False,
        )
        rooms = ChatRoom.objects.filter(Q(user1=new_user) | Q(user2=new_user))
        self.assertEqual(rooms.count(), 0)

    def test_operator_signup_does_not_get_provisioned(self):
        # Already pre-created in setUp; check no per-operator user-rooms exist
        # for jaewon as a regular user (he should only be in proxy + blast rooms).
        jaewon = User.objects.get(email='jaewonkim628@gmail.com')
        # No room where jaewon is the "regular user" with WIT Admin (i.e., his is the
        # blast room, not a regular-user provision)
        from chat.wit_admin import ensure_wit_admin_user
        wit = ensure_wit_admin_user()
        u1, u2 = (jaewon, wit) if jaewon.id < wit.id else (wit, jaewon)
        rooms = ChatRoom.objects.filter(user1=u1, user2=u2)
        # Exactly one room — the blast room — must be flagged as such.
        self.assertEqual(rooms.count(), 1)
        self.assertTrue(rooms.first().is_wit_admin_blast_room)


class InboundFanOutTests(TestCase):
    def setUp(self):
        from django.core.management import call_command
        self.jaewon = User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        self.koyrkr = User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        self.njs = User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        call_command('seed_wit_admin_chats')

    def _wit_admin(self):
        from chat.wit_admin import ensure_wit_admin_user
        return ensure_wit_admin_user()

    def _alice_wit_room(self):
        wit = self._wit_admin()
        u1, u2 = (self.alice, wit) if self.alice.id < wit.id else (wit, self.alice)
        return ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=False)

    def test_user_message_fans_out_to_three_proxy_rooms(self):
        room = self._alice_wit_room()
        Message.objects.create(
            chat_room=room, sender=self.alice, receiver=self._wit_admin(), content='hello',
        )
        # Original counts as 1; expect 3 mirrors in the 3 proxy rooms
        mirrors = Message.objects.filter(is_wit_admin_mirror=True)
        self.assertEqual(mirrors.count(), 3)
        self.assertEqual({m.receiver.email for m in mirrors}, {
            'jaewonkim628@gmail.com', 'koyrkr@gmail.com', 'njs03332@gmail.com',
        })
        for m in mirrors:
            self.assertEqual(m.sender, self.alice)
            self.assertEqual(m.content, 'hello')
            self.assertTrue(m.chat_room.is_wit_admin_proxy)

    def test_wit_admin_sender_does_not_fanout_inbound(self):
        room = self._alice_wit_room()
        wit = self._wit_admin()
        Message.objects.create(chat_room=room, sender=wit, receiver=self.alice, content='from-admin')
        # No inbound mirrors at all — branch 1 must not match outbound direction.
        self.assertEqual(Message.objects.filter(is_wit_admin_mirror=True).count(), 0)


class JaewonReplyFanInTests(TestCase):
    def setUp(self):
        from django.core.management import call_command
        self.jaewon = User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        self.koyrkr = User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        self.njs = User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        call_command('seed_wit_admin_chats')

    def _wit(self):
        from chat.wit_admin import ensure_wit_admin_user
        return ensure_wit_admin_user()

    def _alice_jaewon_proxy(self):
        u1, u2 = (self.alice, self.jaewon) if self.alice.id < self.jaewon.id else (self.jaewon, self.alice)
        return ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=True)

    def _alice_wit_room(self):
        wit = self._wit()
        u1, u2 = (self.alice, wit) if self.alice.id < wit.id else (wit, self.alice)
        return ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=False)

    def test_jaewon_reply_in_proxy_mirrors_to_user_wit_room(self):
        proxy = self._alice_jaewon_proxy()
        Message.objects.create(
            chat_room=proxy, sender=self.jaewon, receiver=self.alice, content='reply',
        )
        wit_room = self._alice_wit_room()
        mirrors = Message.objects.filter(
            chat_room=wit_room, is_wit_admin_mirror=True, sender=self._wit(),
        )
        self.assertEqual(mirrors.count(), 1)
        self.assertEqual(mirrors.first().content, 'reply')
        self.assertEqual(mirrors.first().receiver, self.alice)

    def test_koyrkr_reply_does_not_fanin(self):
        u1, u2 = (self.alice, self.koyrkr) if self.alice.id < self.koyrkr.id else (self.koyrkr, self.alice)
        proxy = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=True)
        Message.objects.create(chat_room=proxy, sender=self.koyrkr, receiver=self.alice, content='nope')
        # No mirror should appear in the WIT Admin room
        wit_room = self._alice_wit_room()
        self.assertEqual(Message.objects.filter(chat_room=wit_room).count(), 0)

    def test_njs_reply_does_not_fanin(self):
        u1, u2 = (self.alice, self.njs) if self.alice.id < self.njs.id else (self.njs, self.alice)
        proxy = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=True)
        Message.objects.create(chat_room=proxy, sender=self.njs, receiver=self.alice, content='nope')
        wit_room = self._alice_wit_room()
        self.assertEqual(Message.objects.filter(chat_room=wit_room).count(), 0)


class JaewonBlastTests(TestCase):
    def setUp(self):
        from django.core.management import call_command
        self.jaewon = User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        self.koyrkr = User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        self.njs = User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        self.bob = User.objects.create_user(username='bob', email='b@e.com', password='x')
        call_command('seed_wit_admin_chats')

    def _wit(self):
        from chat.wit_admin import ensure_wit_admin_user
        return ensure_wit_admin_user()

    def _jaewon_blast_room(self):
        wit = self._wit()
        u1, u2 = (self.jaewon, wit) if self.jaewon.id < wit.id else (wit, self.jaewon)
        return ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_blast_room=True)

    def test_jaewon_blast_reaches_all_users(self):
        blast = self._jaewon_blast_room()
        Message.objects.create(
            chat_room=blast, sender=self.jaewon, receiver=self._wit(),
            content='announcement',
        )
        # Mirror to alice's and bob's WIT Admin rooms (sender=wit)
        wit = self._wit()
        for user in (self.alice, self.bob):
            u1, u2 = (user, wit) if user.id < wit.id else (wit, user)
            wit_room = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=False)
            user_msgs = Message.objects.filter(
                chat_room=wit_room, is_wit_admin_mirror=True, sender=wit,
            )
            self.assertEqual(user_msgs.count(), 1, f"Missing blast for {user.username}")
            self.assertEqual(user_msgs.first().content, 'announcement')

    def test_jaewon_blast_mirrors_into_observer_logs(self):
        blast = self._jaewon_blast_room()
        Message.objects.create(
            chat_room=blast, sender=self.jaewon, receiver=self._wit(),
            content='announcement',
        )
        wit = self._wit()
        for op in (self.koyrkr, self.njs):
            u1, u2 = (wit, op) if wit.id < op.id else (op, wit)
            log = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_blast_room=True)
            mirrors = Message.objects.filter(
                chat_room=log, is_wit_admin_mirror=True, sender=wit,
            )
            self.assertEqual(mirrors.count(), 1, f"Missing log entry for {op.username}")

    def test_koyrkr_typing_in_own_blast_log_does_nothing(self):
        wit = self._wit()
        u1, u2 = (wit, self.koyrkr) if wit.id < self.koyrkr.id else (self.koyrkr, wit)
        log = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_blast_room=True)
        Message.objects.create(chat_room=log, sender=self.koyrkr, receiver=wit, content='leak')
        # No fan-out: no messages anywhere except the original in koyrkr's log
        self.assertEqual(Message.objects.exclude(chat_room=log).count(), 0)


class LoopGuardTests(TestCase):
    def setUp(self):
        from django.core.management import call_command
        User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        call_command('seed_wit_admin_chats')

    def test_inbound_produces_exactly_three_mirrors_no_recursion(self):
        from chat.wit_admin import ensure_wit_admin_user
        wit = ensure_wit_admin_user()
        u1, u2 = (self.alice, wit) if self.alice.id < wit.id else (wit, self.alice)
        room = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=False)
        Message.objects.create(chat_room=room, sender=self.alice, receiver=wit, content='no-loop')
        # Total messages = 1 original + 3 mirrors = 4. Anything more = infinite loop.
        self.assertEqual(Message.objects.count(), 4)
        self.assertEqual(Message.objects.filter(is_wit_admin_mirror=True).count(), 3)

    def test_blast_produces_n_plus_two_no_recursion(self):
        from chat.wit_admin import ensure_wit_admin_user
        wit = ensure_wit_admin_user()
        jaewon = User.objects.get(email='jaewonkim628@gmail.com')
        u1, u2 = (jaewon, wit) if jaewon.id < wit.id else (wit, jaewon)
        blast = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_blast_room=True)
        Message.objects.create(chat_room=blast, sender=jaewon, receiver=wit, content='broadcast')
        # 1 original + 1 (alice WIT room) + 2 (observer logs) = 4
        self.assertEqual(Message.objects.count(), 4)
        self.assertEqual(Message.objects.filter(is_wit_admin_mirror=True).count(), 3)


class ChatListPinTests(TestCase):
    def setUp(self):
        from django.core.management import call_command
        User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        self.charlie = User.objects.create_user(username='charlie', email='c@e.com', password='x')
        call_command('seed_wit_admin_chats')

    def _list(self, user):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from chat.views import ChatRoomList
        factory = APIRequestFactory()
        req = factory.get('/api/chat/rooms/')
        force_authenticate(req, user=user)
        view = ChatRoomList.as_view()
        resp = view(req)
        return resp.data

    def test_wit_admin_room_appears_first_for_regular_user(self):
        # Make charlie send alice a message to ensure their non-WIT chat has a last_message_time
        from chat.models import get_or_create_chat_room
        from chat.wit_admin import ensure_wit_admin_user
        room = get_or_create_chat_room(self.alice, self.charlie)
        Message.objects.create(chat_room=room, sender=self.charlie, receiver=self.alice, content='hi')
        data = self._list(self.alice)
        results = data.get('results', data)  # paginated or not
        first = results[0]
        wit = ensure_wit_admin_user()
        u1, u2 = (self.alice, wit) if self.alice.id < wit.id else (wit, self.alice)
        wit_room = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=False)
        self.assertEqual(first['id'], wit_room.id)

    def test_wit_admin_room_appears_even_when_empty(self):
        # Alice has not messaged WIT Admin, has no other chats
        data = self._list(self.alice)
        results = data.get('results', data)
        self.assertGreaterEqual(len(results), 1)


class WebSocketBroadcastTests(TestCase):
    def setUp(self):
        from django.core.management import call_command
        self.jaewon = User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        self.koyrkr = User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        self.njs = User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        call_command('seed_wit_admin_chats')

    def _wit(self):
        from chat.wit_admin import ensure_wit_admin_user
        return ensure_wit_admin_user()

    def _alice_wit_room(self):
        wit = self._wit()
        u1, u2 = (self.alice, wit) if self.alice.id < wit.id else (wit, self.alice)
        return ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=False)

    def test_inbound_fanout_broadcasts_for_each_mirror(self):
        from unittest.mock import patch
        room = self._alice_wit_room()
        with patch('chat.views.async_to_sync') as mock_ats:
            # async_to_sync wraps group_send; we count its invocations
            mock_ats.return_value = lambda *a, **kw: None
            Message.objects.create(
                chat_room=room, sender=self.alice, receiver=self._wit(), content='hello',
            )
        # Each mirror produces:
        #   1 chat.message + 2 chat.list.update = 3 group_sends
        # x 3 mirrors = 9 invocations.
        self.assertEqual(mock_ats.call_count, 9)

    def test_jaewon_blast_broadcasts_for_each_recipient_and_observer(self):
        from unittest.mock import patch
        wit = self._wit()
        u1, u2 = (self.jaewon, wit) if self.jaewon.id < wit.id else (wit, self.jaewon)
        blast = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_blast_room=True)
        with patch('chat.views.async_to_sync') as mock_ats:
            mock_ats.return_value = lambda *a, **kw: None
            Message.objects.create(
                chat_room=blast, sender=self.jaewon, receiver=wit, content='announcement',
            )
        # 1 user (alice) + 2 observers (koyrkr, njs) = 3 mirrors,
        # each with 3 sends = 9 invocations.
        self.assertEqual(mock_ats.call_count, 9)
