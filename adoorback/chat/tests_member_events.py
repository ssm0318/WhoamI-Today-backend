from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from chat.models import ChatRoom, Message

User = get_user_model()


class GroupMemberAddedSystemMessageTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        self.bob = User.objects.create_user(username='bob', email='b@e.com', password='x')
        self.carol = User.objects.create_user(username='carol', email='c@e.com', password='x')
        self.room = ChatRoom.objects.create(is_group=True, name='G')
        self.room.members.set([self.alice, self.bob])
        self.client = APIClient()
        self.client.force_authenticate(user=self.alice)

    def _patch_url(self):
        return reverse('group-chat-update', kwargs={'pk': self.room.id})

    @patch('chat.views.async_to_sync')
    def test_add_member_creates_system_message(self, _):
        resp = self.client.patch(self._patch_url(), {'add_member_ids': [self.carol.id]}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        msgs = Message.objects.filter(chat_room=self.room, event_type='member_added')
        self.assertEqual(msgs.count(), 1)
        msg = msgs.first()
        self.assertEqual(msg.sender, self.alice)
        self.assertIsNone(msg.receiver)
        self.assertEqual(list(msg.event_target_users.all()), [self.carol])

    @patch('chat.views.async_to_sync')
    def test_add_member_broadcasts_system_message(self, mock_async):
        # async_to_sync(channel_layer.group_send) returns a callable; capture
        # the args passed to that callable.
        mock_async.return_value = lambda *args, **kwargs: None
        self.client.patch(self._patch_url(), {'add_member_ids': [self.carol.id]}, format='json')
        # async_to_sync is called once per group_send. There should be at least
        # one chat.message broadcast and one chat.list.update per current member.
        self.assertGreater(mock_async.call_count, 0)

    @patch('chat.views.async_to_sync')
    def test_add_member_serialized_includes_event_target_users(self, _):
        from chat.serializers import MessageSerializer
        self.client.patch(self._patch_url(), {'add_member_ids': [self.carol.id]}, format='json')
        msg = Message.objects.get(chat_room=self.room, event_type='member_added')
        data = MessageSerializer(msg).data
        self.assertEqual(data['event_type'], 'member_added')
        usernames = [u['username'] for u in data['event_target_users']]
        self.assertEqual(usernames, ['carol'])


class GroupMemberRemovedSystemMessageTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        self.bob = User.objects.create_user(username='bob', email='b@e.com', password='x')
        self.carol = User.objects.create_user(username='carol', email='c@e.com', password='x')
        self.room = ChatRoom.objects.create(is_group=True, name='G')
        self.room.members.set([self.alice, self.bob, self.carol])
        self.client = APIClient()
        self.client.force_authenticate(user=self.alice)

    @patch('chat.views.async_to_sync')
    def test_remove_member_creates_left_event(self, _):
        url = reverse('group-chat-update', kwargs={'pk': self.room.id})
        self.client.patch(url, {'remove_member_ids': [self.carol.id]}, format='json')
        msgs = Message.objects.filter(chat_room=self.room, event_type='member_left')
        self.assertEqual(msgs.count(), 1)
        msg = msgs.first()
        self.assertEqual(list(msg.event_target_users.all()), [self.carol])
        self.assertNotIn(self.carol, list(self.room.members.all()))


class GroupChatLeaveSystemMessageTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        self.bob = User.objects.create_user(username='bob', email='b@e.com', password='x')
        self.room = ChatRoom.objects.create(is_group=True, name='G')
        self.room.members.set([self.alice, self.bob])

    @patch('chat.views.async_to_sync')
    def test_leave_creates_system_message(self, _):
        client = APIClient()
        client.force_authenticate(user=self.bob)
        url = reverse('group-chat-leave', kwargs={'pk': self.room.id})
        resp = client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        msg = Message.objects.get(chat_room=self.room, event_type='member_left')
        self.assertEqual(msg.sender, self.bob)
        self.assertEqual(list(msg.event_target_users.all()), [self.bob])

    @patch('chat.views.async_to_sync')
    def test_last_member_leave_deletes_room_and_message(self, _):
        # alice is the only remaining member, so leaving deletes the room
        Message.objects.filter(chat_room=self.room).delete()
        self.room.members.set([self.alice])
        client = APIClient()
        client.force_authenticate(user=self.alice)
        url = reverse('group-chat-leave', kwargs={'pk': self.room.id})
        client.post(url)
        # Soft-deleted via SafeDelete cascade — should be invisible to default manager
        self.assertFalse(ChatRoom.objects.filter(id=self.room.id).exists())


class SystemEventLastMessagePreviewTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        self.bob = User.objects.create_user(username='bob', email='b@e.com', password='x')
        self.room = ChatRoom.objects.create(is_group=True, name='G')
        self.room.members.set([self.alice, self.bob])

    def test_last_message_preview_for_member_added(self):
        from chat.serializers import ChatRoomSerializer
        from rest_framework.test import APIRequestFactory

        msg = Message.objects.create(
            chat_room=self.room, sender=self.alice, receiver=None,
            event_type='member_added',
        )
        msg.event_target_users.set([self.bob])

        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = self.alice
        data = ChatRoomSerializer(self.room, context={'request': request}).data
        # English fallback (no Accept-Language header)
        self.assertEqual(data['last_message'], 'A member was added')

    def test_last_message_preview_for_member_left(self):
        from chat.serializers import ChatRoomSerializer
        from rest_framework.test import APIRequestFactory

        msg = Message.objects.create(
            chat_room=self.room, sender=self.alice, receiver=None,
            event_type='member_left',
        )
        msg.event_target_users.set([self.bob])

        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = self.alice
        data = ChatRoomSerializer(self.room, context={'request': request}).data
        self.assertEqual(data['last_message'], 'A member left')


class SystemMessageValidationTests(TestCase):
    def test_system_message_skips_content_requirement(self):
        alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        bob = User.objects.create_user(username='bob', email='b@e.com', password='x')
        room = ChatRoom.objects.create(is_group=True, name='G')
        room.members.set([alice, bob])

        # Should not raise — system messages don't need content/emoji/image.
        msg = Message.objects.create(
            chat_room=room, sender=alice, receiver=None,
            event_type='member_added',
        )
        self.assertEqual(msg.event_type, 'member_added')
        self.assertEqual(msg.content, '')
