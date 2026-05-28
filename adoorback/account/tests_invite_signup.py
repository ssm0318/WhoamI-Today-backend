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

    def test_inviter_can_be_looked_up_by_invite_code(self):
        self.inviter.invite_code = 'ABC12345'
        self.inviter.save(update_fields=['invite_code'])

        response = self.client.post('/api/user/signup/inviter-username/', {
            'invite_code': self.inviter.invite_code,
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['inviter_id'], self.inviter.id)
        self.assertEqual(response.data['username'], self.inviter.username)
        self.assertEqual(response.data['invite_code'], self.inviter.invite_code)

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


class CaseInsensitiveSignupTests(APITestCase):
    """Regression for the bug where capitalizing the first letter of an email
    let the same person create a second account. Email AND username uniqueness
    must be case-insensitive across the precheck endpoints, the final signup
    endpoint, and the login lookup."""

    def setUp(self):
        self.existing = User.objects.create_user(
            username='existing_user',
            email='existing@example.com',
            password='password123',
            current_ver='version_q',
            user_group='group_q_first',
        )
        self.inviter = User.objects.create_user(
            username='inviter',
            email='inviter@example.com',
            password='password123',
            current_ver='version_q',
            user_group='group_q_first',
        )

    def test_email_precheck_rejects_case_variant(self):
        # Precheck endpoints map the unique-code ValidationError to the
        # project's ExistingEmail exception, which returns 406 Not Acceptable
        # (see adoorback/utils/exceptions.py).
        response = self.client.post('/api/user/signup/email/', {'email': 'EXISTING@example.com'})
        self.assertEqual(response.status_code, status.HTTP_406_NOT_ACCEPTABLE)

    def test_username_precheck_rejects_case_variant(self):
        response = self.client.post('/api/user/signup/username/', {'username': 'Existing_User'})
        self.assertEqual(response.status_code, status.HTTP_406_NOT_ACCEPTABLE)

    def test_signup_rejects_case_variant_of_existing_email(self):
        payload = {
            'email': 'Existing@example.com',
            'username': 'someone_new',
            'password': 'password123',
            'inviter_id': self.inviter.id,
        }
        response = self.client.post('/api/user/signup/', payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # No second account got created
        self.assertEqual(User.objects.filter(email__iexact='existing@example.com').count(), 1)

    def test_signup_rejects_case_variant_of_existing_username(self):
        payload = {
            'email': 'brand_new@example.com',
            'username': 'EXISTING_USER',
            'password': 'password123',
            'inviter_id': self.inviter.id,
        }
        response = self.client.post('/api/user/signup/', payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.filter(username__iexact='existing_user').count(), 1)

    def test_signup_normalizes_email_and_username_to_lowercase(self):
        payload = {
            'email': 'NewPerson@Example.Com',
            'username': 'NewPerson',
            'password': 'password123',
            'inviter_id': self.inviter.id,
        }
        response = self.client.post('/api/user/signup/', payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = User.objects.get(email='newperson@example.com')
        self.assertEqual(created.username, 'newperson')

    def test_login_accepts_case_variant_of_stored_email(self):
        response = self.client.post('/api/user/login/', {
            'username': 'EXISTING@example.com',
            'password': 'password123',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_login_accepts_case_variant_of_stored_username(self):
        response = self.client.post('/api/user/login/', {
            'username': 'Existing_User',
            'password': 'password123',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
