from django.test import TestCase
from django.contrib.auth import get_user_model
from account.models import Connection
from account.serializers import UserProfileSerializer
from rest_framework.test import APIRequestFactory, APIClient

User = get_user_model()

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
