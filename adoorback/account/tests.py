from django.test import TestCase
from django.contrib.auth import get_user_model
from account.models import Connection, Follow
from account.serializers import UserProfileSerializer
from rest_framework.test import APIRequestFactory

User = get_user_model()

class ProfileCountTests(TestCase):
    def setUp(self):
        self.me = User.objects.create_user(username='test_cnt_me', email='test_cnt_me@example.com', password='password')
        self.friend = User.objects.create_user(username='test_cnt_friend', email='test_cnt_friend@example.com', password='password')
        self.follower = User.objects.create_user(username='test_cnt_follower', email='test_cnt_follower@example.com', password='password')
        self.following = User.objects.create_user(username='test_cnt_following', email='test_cnt_following@example.com', password='password')

        # Setup Friend (Connection)
        Connection.objects.create(user1=self.me, user2=self.friend, user1_choice='friend', user2_choice='friend')

        # Setup Follower
        Follow.objects.create(follower=self.follower, followed=self.me)

        # Setup Following
        Follow.objects.create(follower=self.me, followed=self.following)
    
    def test_counts(self):
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = self.me
        context = {'request': request}

        serializer = UserProfileSerializer(self.me, context=context)
        data = serializer.data

        self.assertEqual(data.get('friend_count'), 1)
        self.assertEqual(data.get('follower_count'), 1)
        self.assertEqual(data.get('following_count'), 1)


class ConnectionAutoUnfollowTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='user_a', email='user_a@example.com', password='password')
        self.user_b = User.objects.create_user(username='user_b', email='user_b@example.com', password='password')

    def test_auto_unfollow(self):
        # A follows B
        Follow.objects.create(follower=self.user_a, followed=self.user_b)
        # B follows A
        Follow.objects.create(follower=self.user_b, followed=self.user_a)

        self.assertTrue(Follow.objects.filter(follower=self.user_a, followed=self.user_b).exists())
        self.assertTrue(Follow.objects.filter(follower=self.user_b, followed=self.user_a).exists())

        # Establish Connection (Friendship)
        Connection.objects.create(user1=self.user_a, user2=self.user_b, user1_choice='friend', user2_choice='friend')

        # Check if Follow objects are removed
        self.assertFalse(Follow.objects.filter(follower=self.user_a, followed=self.user_b).exists())
        self.assertFalse(Follow.objects.filter(follower=self.user_b, followed=self.user_a).exists())
