from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse

from account.models import Connection
from ping.models import PingRequest, PingRoom, Ping

User = get_user_model()


class PingRequestModelTests(APITestCase):
    """Test PingRequest model constraints."""

    def setUp(self):
        self.user_a = User.objects.create_user(
            username='user_a', email='a@test.com', password='password'
        )
        self.user_b = User.objects.create_user(
            username='user_b', email='b@test.com', password='password'
        )

    def test_create_ping_request(self):
        req = PingRequest.objects.create(requester=self.user_a, requestee=self.user_b)
        self.assertIsNone(req.accepted)
        self.assertEqual(str(req), f"PingRequest from {self.user_a} to {self.user_b} (pending)")

    def test_accept_ping_request(self):
        req = PingRequest.objects.create(requester=self.user_a, requestee=self.user_b)
        req.accepted = True
        req.save()
        self.assertTrue(req.accepted)

    def test_decline_ping_request(self):
        req = PingRequest.objects.create(requester=self.user_a, requestee=self.user_b)
        req.accepted = False
        req.save()
        self.assertFalse(req.accepted)


class PingRequestAPITests(APITestCase):
    """Test PingRequest API endpoints."""

    def setUp(self):
        self.user_a = User.objects.create_user(
            username='user_a', email='a@test.com', password='password'
        )
        self.user_b = User.objects.create_user(
            username='user_b', email='b@test.com', password='password'
        )
        self.friend = User.objects.create_user(
            username='friend', email='friend@test.com', password='password'
        )
        # user_a and friend are connected
        Connection.objects.create(
            user1=self.user_a, user2=self.friend,
            user1_choice='friend', user2_choice='friend'
        )

    def test_create_ping_request_to_non_friend(self):
        """Should be able to create a ping request to a non-friend."""
        self.client.force_authenticate(user=self.user_a)
        url = reverse('ping-request-create')
        data = {'requestee_id': self.user_b.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PingRequest.objects.count(), 1)

    def test_cannot_create_ping_request_to_friend(self):
        """Should not be able to create a ping request to an existing friend."""
        self.client.force_authenticate(user=self.user_a)
        url = reverse('ping-request-create')
        data = {'requestee_id': self.friend.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_create_duplicate_ping_request(self):
        """Should not be able to create duplicate ping requests."""
        PingRequest.objects.create(requester=self.user_a, requestee=self.user_b)
        self.client.force_authenticate(user=self.user_a)
        url = reverse('ping-request-create')
        data = {'requestee_id': self.user_b.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_send_ping_request_to_self(self):
        """Should not be able to send a ping request to yourself."""
        self.client.force_authenticate(user=self.user_a)
        url = reverse('ping-request-create')
        data = {'requestee_id': self.user_a.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_received_pending_requests(self):
        """Should list pending requests received by current user."""
        PingRequest.objects.create(requester=self.user_a, requestee=self.user_b)
        self.client.force_authenticate(user=self.user_b)
        url = reverse('ping-request-create')  # GET on same URL = list
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)

    def test_list_sent_requests(self):
        """Should list requests sent by current user."""
        PingRequest.objects.create(requester=self.user_a, requestee=self.user_b)
        self.client.force_authenticate(user=self.user_a)
        url = reverse('ping-request-sent-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)

    def test_accept_ping_request(self):
        """Requestee should be able to accept a ping request."""
        req = PingRequest.objects.create(requester=self.user_a, requestee=self.user_b)
        self.client.force_authenticate(user=self.user_b)
        url = reverse('ping-request-update', kwargs={'pk': req.pk})
        response = self.client.patch(url, {'accepted': True})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        req.refresh_from_db()
        self.assertTrue(req.accepted)

    def test_decline_ping_request(self):
        """Requestee should be able to decline a ping request."""
        req = PingRequest.objects.create(requester=self.user_a, requestee=self.user_b)
        self.client.force_authenticate(user=self.user_b)
        url = reverse('ping-request-update', kwargs={'pk': req.pk})
        response = self.client.patch(url, {'accepted': False})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        req.refresh_from_db()
        self.assertFalse(req.accepted)

    def test_requester_cannot_accept_own_request(self):
        """Requester should NOT be able to accept their own request."""
        req = PingRequest.objects.create(requester=self.user_a, requestee=self.user_b)
        self.client.force_authenticate(user=self.user_a)
        url = reverse('ping-request-update', kwargs={'pk': req.pk})
        response = self.client.patch(url, {'accepted': True})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PingWithRequestEnforcementTests(APITestCase):
    """Test that ping sending enforces the request system for non-friends."""

    def setUp(self):
        self.user_a = User.objects.create_user(
            username='user_a', email='a@test.com', password='password'
        )
        self.user_b = User.objects.create_user(
            username='user_b', email='b@test.com', password='password'
        )
        self.friend = User.objects.create_user(
            username='friend', email='friend@test.com', password='password'
        )
        Connection.objects.create(
            user1=self.user_a, user2=self.friend,
            user1_choice='friend', user2_choice='friend'
        )

    def test_friend_can_ping_directly(self):
        """Friends should be able to ping without a request."""
        self.client.force_authenticate(user=self.user_a)
        url = reverse('ping_list', kwargs={'pk': self.friend.pk})
        response = self.client.post(url, {'content': 'Hello friend!'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PingRequest.objects.count(), 0)

    def test_non_friend_first_ping_creates_request(self):
        """First ping to non-friend should auto-create a PingRequest."""
        self.client.force_authenticate(user=self.user_a)
        url = reverse('ping_list', kwargs={'pk': self.user_b.pk})
        response = self.client.post(url, {'content': 'Hey stranger!'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PingRequest.objects.count(), 1)
        req = PingRequest.objects.first()
        self.assertEqual(req.requester, self.user_a)
        self.assertEqual(req.requestee, self.user_b)
        self.assertIsNone(req.accepted)

    def test_non_friend_declined_request_blocks_ping(self):
        """If request is declined, further pings should be blocked."""
        PingRequest.objects.create(
            requester=self.user_a, requestee=self.user_b, accepted=False
        )
        self.client.force_authenticate(user=self.user_a)
        url = reverse('ping_list', kwargs={'pk': self.user_b.pk})
        response = self.client.post(url, {'content': 'Trying again...'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_friend_accepted_request_allows_ping(self):
        """If request is accepted, pings should be allowed."""
        PingRequest.objects.create(
            requester=self.user_a, requestee=self.user_b, accepted=True
        )
        self.client.force_authenticate(user=self.user_a)
        url = reverse('ping_list', kwargs={'pk': self.user_b.pk})
        response = self.client.post(url, {'content': 'Hello!'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_ping_room_list_includes_request_status(self):
        """PingRoomList should include request_status field."""
        # Create a ping room with a ping
        PingRequest.objects.create(
            requester=self.user_a, requestee=self.user_b, accepted=True
        )
        self.client.force_authenticate(user=self.user_a)
        # Send a ping to create the room
        ping_url = reverse('ping_list', kwargs={'pk': self.user_b.pk})
        self.client.post(ping_url, {'content': 'Hello!'})

        url = reverse('ping-room-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        if len(results) > 0:
            self.assertIn('request_status', results[0])
