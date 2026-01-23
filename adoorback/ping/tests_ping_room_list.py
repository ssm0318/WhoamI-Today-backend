
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ping.models import Ping, get_or_create_ping_room

User = get_user_model()

class PingRoomListTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='user', email='user@example.com', password='password')
        self.user2 = User.objects.create_user(username='user2', email='user2@example.com', password='password')
        self.user3 = User.objects.create_user(username='user3', email='user3@example.com', password='password')
        
        # Make them friends (connected) - simpler way if connection logic allows, 
        # but for PingRoom we just need the room to exist. 
        # However, PingRoom.clean enforces connection.
        # Let's bypass full connection logic for unit test data setup if possible, 
        # or just create PingRooms directly if the model allows it without full validation in tests
        # Or mock the connection check if needed. 
        # Actually PingRoom check is in clean(), which is called on full_clean(), which saves call?
        # Let's try creating rooms directly first. 
        
        # Mocking is_connected to True for simplicity or create connection 
        # But connection logic might be complex. Let's see if we can create PingRoom directly.
        # PingRoom save() calls full_clean() so clean() will run.
        # We need to make them connected.
        
        self.make_connected(self.user, self.user2)
        self.make_connected(self.user, self.user3)

        self.client.login(username='user', password='password')
        self.url = reverse('ping-room-list')

    def make_connected(self, u1, u2):
        from account.models import Connection
        Connection.objects.create(user1=u1, user2=u2, user1_choice='friend', user2_choice='friend')

    def test_get_ping_room_list(self):
        # Room 1: User <-> User2
        room1 = get_or_create_ping_room(self.user, self.user2)
        Ping.objects.create(sender=self.user2, receiver=self.user, ping_room=room1, content="Hello from user2")
        
        # Room 2: User <-> User3
        room2 = get_or_create_ping_room(self.user, self.user3)
        p2 = Ping.objects.create(sender=self.user3, receiver=self.user, ping_room=room2, content="Hi from user3")
        
        # Room 2 message is newer, so it should be first?
        # Let's add another newer message to Room 1
        import time
        time.sleep(0.1) 
        p3 = Ping.objects.create(sender=self.user, receiver=self.user2, ping_room=room1, content="Reply from user")
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Handle pagination
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 2)
        
        # Room 1 should be first because p3 is latest
        self.assertEqual(results[0]['id'], room1.id)
        self.assertEqual(results[0]['opponent']['username'], 'user2')
        self.assertEqual(results[0]['last_message'], "Reply from user")
        
        # Room 2 should be second
        self.assertEqual(results[1]['id'], room2.id)
        
    def test_unread_count(self):
        room1 = get_or_create_ping_room(self.user, self.user2)
        # 2 unread messages from user2 to user
        Ping.objects.create(sender=self.user2, receiver=self.user, ping_room=room1, content="Msg 1")
        Ping.objects.create(sender=self.user2, receiver=self.user, ping_room=room1, content="Msg 2")
        # 1 read message
        Ping.objects.create(sender=self.user2, receiver=self.user, ping_room=room1, content="Msg 3", is_read=True)
        # 1 message from user to user2 (should not count)
        Ping.objects.create(sender=self.user, receiver=self.user2, ping_room=room1, content="My reply")
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        results = response.data.get('results', response.data)
        room_data = results[0]
        self.assertEqual(room_data['unread_count'], 2)
        
