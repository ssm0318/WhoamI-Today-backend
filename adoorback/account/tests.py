from django.test import TestCase
from django.contrib.auth import get_user_model
from account.models import Connection
from account.serializers import UserProfileSerializer
from rest_framework.test import APIRequestFactory

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
