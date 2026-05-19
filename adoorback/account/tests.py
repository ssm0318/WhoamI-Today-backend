from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from account.models import Connection, FriendEvaluation, FriendRequest
from account.serializers import UserProfileSerializer
from rest_framework import status
from rest_framework.test import APIRequestFactory, APIClient, APITestCase

User = get_user_model()


class FriendEvaluationRequiredTests(APITestCase):
    def setUp(self):
        self.requester = User.objects.create_user(
            username='friend_eval_requester',
            email='friend_eval_requester@example.com',
            password='password',
        )
        self.requestee = User.objects.create_user(
            username='friend_eval_requestee',
            email='friend_eval_requestee@example.com',
            password='password',
        )
        User.objects.create_superuser(
            username='friend_eval_admin',
            email='friend_eval_admin@example.com',
            password='password',
        )
        self.client.force_authenticate(user=self.requester)
        self.create_url = reverse('user-friend-request-list')

    def _valid_request_payload(self):
        return {
            'requester_id': self.requester.id,
            'requestee_id': self.requestee.id,
            'requester_choice': 'friend',
            'evaluation_closeness': 4,
            'evaluation_relationship_type': 'school_friend',
        }

    def _accept_url(self):
        return reverse('user-friend-request-update', args=[self.requester.id])

    def _create_pending_request(self):
        return FriendRequest.objects.create(
            requester=self.requester,
            requestee=self.requestee,
            requester_choice='friend',
            accepted=None,
        )

    def test_sending_friend_request_requires_evaluation(self):
        response = self.client.post(self.create_url, {
            'requester_id': self.requester.id,
            'requestee_id': self.requestee.id,
            'requester_choice': 'friend',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(FriendRequest.objects.exists())
        self.assertFalse(FriendEvaluation.objects.exists())

    def test_sending_friend_request_rejects_skipped_evaluation(self):
        payload = self._valid_request_payload()
        payload.pop('evaluation_closeness')
        payload.pop('evaluation_relationship_type')
        payload['evaluation_skipped'] = True

        response = self.client.post(self.create_url, payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(FriendRequest.objects.exists())
        self.assertFalse(FriendEvaluation.objects.exists())

    def test_accepting_friend_request_requires_evaluation(self):
        self._create_pending_request()
        self.client.force_authenticate(user=self.requestee)

        response = self.client.patch(self._accept_url(), {
            'accepted': True,
            'requestee_choice': 'friend',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(FriendEvaluation.objects.filter(
            evaluator=self.requestee,
            evaluated_user=self.requester,
        ).exists())

    def test_accepting_friend_request_rejects_skipped_evaluation(self):
        self._create_pending_request()
        self.client.force_authenticate(user=self.requestee)

        response = self.client.patch(self._accept_url(), {
            'accepted': True,
            'requestee_choice': 'friend',
            'evaluation_skipped': True,
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(FriendEvaluation.objects.filter(
            evaluator=self.requestee,
            evaluated_user=self.requester,
        ).exists())

class ProfileCountTests(TestCase):
    def setUp(self):
        self.me = User.objects.create_user(username='test_cnt_me', email='test_cnt_me@example.com', password='password')
        self.friend = User.objects.create_user(username='test_cnt_friend', email='test_cnt_friend@example.com', password='password')

        # Setup Friend (Connection)
        Connection.objects.create(user1=self.me, user2=self.friend, user1_choice='friend', user2_choice='friend')

    def test_counts(self):
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = self.me
        context = {'request': request}

        serializer = UserProfileSerializer(self.me, context=context)
        data = serializer.data

        self.assertEqual(data.get('friend_count'), 1)


class CurrentUserNoteStatusTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='test_user',
            password='password',
            email='test@example.com',
            timezone='Asia/Seoul'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = '/api/user/me/note-status/'

    def test_note_status_without_note(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['has_posted_note_today'])

    def test_note_status_with_note_today(self):
        from note.models import Note
        Note.objects.create(author=self.user, content='test note today')
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['has_posted_note_today'])
