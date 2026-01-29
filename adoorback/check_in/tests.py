from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from check_in.models import CheckIn
from account.models import Connection, Follow

User = get_user_model()

class CheckInVisibilityTests(TestCase):
    def setUp(self):
        # Create users
        self.author = User.objects.create_user(username='author', email='author@test.com', password='password')
        self.friend = User.objects.create_user(username='friend', email='friend@test.com', password='password')
        self.close_friend = User.objects.create_user(username='cf', email='cf@test.com', password='password')
        self.follower = User.objects.create_user(username='follower', email='follower@test.com', password='password')
        self.stranger = User.objects.create_user(username='stranger', email='stranger@test.com', password='password')

        # Setup relationships
        # Friend
        Connection.objects.create(user1=self.author, user2=self.friend, user1_choice='friend', user2_choice='friend')
        
        # Close Friend
        conn_cf = Connection.objects.create(user1=self.author, user2=self.close_friend, user1_choice='close_friend', user2_choice='friend')
        # Upgrade to close friend
        conn_cf.user2_upgrade_time = timezone.now() - timedelta(days=1)
        conn_cf.save()
        self.author.favorites.add(self.close_friend)

        # Follower (following author)
        Follow.objects.create(follower=self.follower, followed=self.author)

    def create_check_in(self, visibility):
        return CheckIn.objects.create(
            user=self.author,
            is_active=True,
            description="Test CheckIn",
            visibility=visibility
        )

    def test_public_visibility(self):
        # Public implies everyone can see
        check_in = self.create_check_in(['public', 'friends', 'close_friends', 'followers'])
        self.assertTrue(check_in.is_audience(self.stranger))
        self.assertTrue(check_in.is_audience(self.friend))
        self.assertTrue(check_in.is_audience(self.close_friend))
        self.assertTrue(check_in.is_audience(self.follower))

    def test_followers_visibility(self):
        check_in = self.create_check_in(['followers'])
        self.assertFalse(check_in.is_audience(self.stranger))
        self.assertTrue(check_in.is_audience(self.follower))        
        self.assertTrue(check_in.is_audience(self.follower))
        self.assertFalse(check_in.is_audience(self.friend))
        
    def test_friends_visibility(self):
        check_in = self.create_check_in(['friends'])
        self.assertFalse(check_in.is_audience(self.stranger))
        self.assertFalse(check_in.is_audience(self.follower))
        self.assertTrue(check_in.is_audience(self.friend))
        self.assertTrue(check_in.is_audience(self.close_friend)) # Close Friend is also a Friend (is_connected=True)

    def test_close_friends_visibility(self):
        check_in = self.create_check_in(['close_friends'])
        self.assertFalse(check_in.is_audience(self.stranger))
        self.assertFalse(check_in.is_audience(self.follower))
        self.assertFalse(check_in.is_audience(self.friend))
        self.assertTrue(check_in.is_audience(self.close_friend))

    def test_multiple_visibility(self):
        check_in = self.create_check_in(['friends', 'followers'])
        self.assertTrue(check_in.is_audience(self.friend))
        self.assertTrue(check_in.is_audience(self.follower))
        self.assertFalse(check_in.is_audience(self.stranger))

    def test_visibility_validation(self):
        from check_in.serializers import MyCheckInSerializer
        # Test empty visibility
        data = {
            'is_active': True,
            'visibility': [],
            'description': 'test'
        }
        serializer = MyCheckInSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('visibility', serializer.errors)
        
        # Test valid visibility
        data['visibility'] = ['public']
        serializer = MyCheckInSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_missing_visibility_key(self):
        from check_in.serializers import MyCheckInSerializer
        # Test completely missing visibility key
        data = {
            'is_active': True,
            'description': 'test no visibility'
        }
        serializer = MyCheckInSerializer(data=data)
        self.assertFalse(serializer.is_valid(), "Serializer should be invalid when visibility key is missing")
        self.assertIn('visibility', serializer.errors)

