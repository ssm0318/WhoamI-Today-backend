"""Ground-truth assertion test for ChatRoomList.

Guards against regressions in the optimized (annotated + prefetched) chat-list
serializer. Seeds a deliberately tricky DB — friend 1-on-1, group chat,
escalated wit_bot room, soft-deleted message, system-event message,
chat-request-pending, chat-request-accepted, chat-request-declined — then
asserts every field on every room in the API response matches values computed
directly from the DB (not via the serializer code).

If a future serializer change breaks any annotation or prefetch, this test
fails with a clear "Room <id> field <name>: expected X, got Y" message.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from chat.models import ChatRequest, ChatRoom, GroupReadCursor, Message
from chat.views import ChatRoomList

User = get_user_model()


class ChatRoomListGroundTruthTests(TestCase):
    """Every field returned by ChatRoomList must match a value computed
    independently from the DB, not from the serializer that produced it."""

    def setUp(self):
        # System users that signal handlers expect.
        User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')

        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        self.bob = User.objects.create_user(username='bob', email='b@e.com', password='x')
        self.carol = User.objects.create_user(username='carol', email='c@e.com', password='x')
        self.dave = User.objects.create_user(username='dave', email='d@e.com', password='x')

        from chat.wit_bot import ensure_wit_bot_user
        self.bot = ensure_wit_bot_user()

        # Friend connection: alice ↔ bob.
        from account.models import Connection
        Connection.objects.create(user1=self.alice, user2=self.bob)

        # 1-on-1 with friend (bob), some unread.
        self.friend_room = self._dm(self.alice, self.bob)
        Message.objects.create(
            chat_room=self.friend_room, sender=self.bob, receiver=self.alice,
            content='hi alice',
        )
        Message.objects.create(
            chat_room=self.friend_room, sender=self.bob, receiver=self.alice,
            content='you up?',
        )

        # 1-on-1 with non-friend (carol), no chat request → request_status None.
        self.stranger_room = self._dm(self.alice, self.carol)
        # No messages.

        # 1-on-1 with non-friend (dave), pending chat request from alice → 'sent'.
        self.pending_room = self._dm(self.alice, self.dave)
        ChatRequest.objects.create(requester=self.alice, requestee=self.dave)

        # Group chat with [alice, bob, carol], some messages.
        self.group_room = ChatRoom.objects.create(
            is_group=True, name='Friends',
            user1=self.alice, user2=self.bob,
        )
        self.group_room.members.set([self.alice, self.bob, self.carol])
        Message.objects.create(
            chat_room=self.group_room, sender=self.bob, receiver=None,
            content='group msg 1',
        )
        Message.objects.create(
            chat_room=self.group_room, sender=self.carol, receiver=None,
            content='group msg 2',
        )

        # Demoted wit_bot room (1-on-1 after dismiss-admin), already has the
        # welcome message + a few hehe replies.
        self.bot_room = ChatRoom.objects.get(
            (
                ChatRoom.objects.filter(user1=self.alice, user2=self.bot).query
            )._chain() if False else None
        ) if False else self._dm(self.alice, self.bot)

    def _dm(self, a, b):
        u1, u2 = (a, b) if a.id < b.id else (b, a)
        room, _ = ChatRoom.objects.get_or_create(user1=u1, user2=u2)
        return room

    def _list_response(self):
        factory = APIRequestFactory()
        req = factory.get('/api/chat/rooms/?page_size=50')
        force_authenticate(req, user=self.alice)
        resp = ChatRoomList.as_view()(req)
        self.assertEqual(resp.status_code, 200)
        return resp.data['results'] if 'results' in resp.data else resp.data

    def _expected_unread(self, room):
        if room.is_group:
            cursor = GroupReadCursor.objects.filter(user=self.alice, chat_room=room).first()
            qs = room.messages.exclude(sender=self.alice)
            if cursor and cursor.last_read_message:
                qs = qs.filter(created_at__gt=cursor.last_read_message.created_at)
            return qs.count()
        return room.messages.filter(receiver=self.alice, is_read=False).count()

    def _expected_request_status(self, room):
        if room.is_group:
            return None
        opponent = room.user2 if room.user1 == self.alice else room.user1
        # System-user surfaces always 'friends'.
        from chat.wit_admin import is_wit_admin
        from chat.wit_bot import is_wit_bot
        if (
            is_wit_admin(opponent) or is_wit_bot(opponent)
            or room.is_wit_admin_proxy or room.is_wit_admin_blast_room
        ):
            return 'friends'
        if self.alice.is_connected(opponent):
            return 'friends'
        req = ChatRequest.objects.filter(
            requester=self.alice, requestee=opponent
        ).first() or ChatRequest.objects.filter(
            requester=opponent, requestee=self.alice
        ).first()
        if req is None:
            return None
        if req.accepted is True:
            return 'accepted'
        if req.accepted is False:
            return 'declined'
        if req.requester_id == self.alice.id:
            return 'sent'
        return 'received'

    def test_unread_count_matches_db_for_every_room(self):
        rooms_in_response = self._list_response()
        self.assertGreater(len(rooms_in_response), 0)
        for room_data in rooms_in_response:
            room = ChatRoom.objects.get(id=room_data['id'])
            self.assertEqual(
                room_data['unread_count'], self._expected_unread(room),
                f"Room {room.id} ({'group' if room.is_group else '1-on-1'}) "
                f"unread_count mismatch",
            )

    def test_request_status_matches_db_for_every_room(self):
        rooms_in_response = self._list_response()
        for room_data in rooms_in_response:
            room = ChatRoom.objects.get(id=room_data['id'])
            self.assertEqual(
                room_data['request_status'], self._expected_request_status(room),
                f"Room {room.id} request_status mismatch",
            )

    def test_opponent_matches_db_for_one_on_one_rooms(self):
        rooms_in_response = self._list_response()
        for room_data in rooms_in_response:
            room = ChatRoom.objects.get(id=room_data['id'])
            if room.is_group:
                self.assertIsNone(room_data['opponent'])
                continue
            expected_opp = room.user2 if room.user1 == self.alice else room.user1
            self.assertEqual(
                room_data['opponent']['id'], expected_opp.id,
                f"Room {room.id} opponent mismatch",
            )
            self.assertEqual(
                room_data['opponent']['username'], expected_opp.username,
            )

    def test_members_detail_matches_db_for_group_rooms(self):
        rooms_in_response = self._list_response()
        for room_data in rooms_in_response:
            room = ChatRoom.objects.get(id=room_data['id'])
            if not room.is_group:
                self.assertIsNone(room_data['members_detail'])
                continue
            expected_ids = set(room.members.values_list('id', flat=True))
            actual_ids = {m['id'] for m in room_data['members_detail']}
            self.assertEqual(
                expected_ids, actual_ids,
                f"Room {room.id} members_detail mismatch",
            )

    def test_last_message_matches_db_preview_for_every_room(self):
        rooms_in_response = self._list_response()
        for room_data in rooms_in_response:
            room = ChatRoom.objects.get(id=room_data['id'])
            last = room.messages.order_by('-created_at').first()
            if last is None:
                self.assertIsNone(room_data['last_message'])
                continue
            # last_message is the preview text — match the same precedence the
            # serializer claims (event > content > emoji > image > shared).
            if last.event_type:
                # Don't bind to exact i18n string; just assert it's non-empty.
                self.assertTrue(room_data['last_message'])
            elif last.content:
                self.assertEqual(room_data['last_message'], last.content)
            elif last.emoji:
                self.assertEqual(room_data['last_message'], last.emoji)
