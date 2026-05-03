from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from account.models import Connection, FriendRequest
from note.models import Note


User = get_user_model()


class InviteOnlySignupTests(APITestCase):
    def setUp(self):
        self.inviter = User.objects.create_user(
            username='inviter',
            email='inviter@example.com',
            password='password123',
            current_ver='version_q',
            user_group='group_q_first',
        )

    def signup_payload(self, **overrides):
        payload = {
            'email': 'new@example.com',
            'username': 'new_user',
            'password': 'password123',
            'inviter_id': self.inviter.id,
        }
        payload.update(overrides)
        return payload

    def test_signup_requires_inviter(self):
        response = self.client.post('/api/user/signup/', self.signup_payload(inviter_id=''))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='new@example.com').exists())

    def test_signup_creates_pending_friend_request_to_inviter(self):
        response = self.client.post('/api/user/signup/', self.signup_payload())

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_user = User.objects.get(email='new@example.com')
        self.assertEqual(new_user.invited_from, self.inviter)
        self.assertEqual(new_user.current_ver, self.inviter.current_ver)
        self.assertTrue(
            FriendRequest.objects.filter(
                requester=new_user,
                requestee=self.inviter,
                accepted__isnull=True,
                requester_choice='friend',
            ).exists()
        )

    def test_invited_user_cannot_post_until_inviter_accepts(self):
        new_user = User.objects.create_user(
            username='new_user',
            email='new@example.com',
            password='password123',
            invited_from=self.inviter,
            current_ver=self.inviter.current_ver,
            user_group=self.inviter.user_group,
        )
        self.client.force_authenticate(user=new_user)

        response = self.client.post('/api/notes/', {
            'content': 'hello',
            'visibility': ['friends'],
        })

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Note.objects.filter(author=new_user).exists())

    def test_invited_user_can_post_after_inviter_accepts(self):
        new_user = User.objects.create_user(
            username='new_user',
            email='new@example.com',
            password='password123',
            invited_from=self.inviter,
            current_ver=self.inviter.current_ver,
            user_group=self.inviter.user_group,
        )
        Connection.objects.create(
            user1=new_user,
            user2=self.inviter,
            user1_choice='friend',
            user2_choice='friend',
        )
        self.client.force_authenticate(user=new_user)

        response = self.client.post('/api/notes/', {
            'content': 'hello',
            'visibility': ['friends'],
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Note.objects.filter(author=new_user).exists())
