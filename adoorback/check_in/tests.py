from datetime import timedelta
from rest_framework.test import APITestCase
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from check_in.models import CheckIn
from account.models import Connection

User = get_user_model()

class CheckInVisibilityTests(APITestCase):
    def setUp(self):
        # Create users
        self.author = User.objects.create_user(username='author', email='author@test.com', password='password')
        self.friend = User.objects.create_user(username='friend', email='friend@test.com', password='password')
        self.close_friend = User.objects.create_user(username='cf', email='cf@test.com', password='password')
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

    def create_check_in(self, visibility):
        return CheckIn.objects.create(
            user=self.author,
            is_active=True,
            description="Test CheckIn",
            visibility=visibility
        )

    def test_public_visibility(self):
        # Public implies everyone can see
        check_in = self.create_check_in(['public', 'friends', 'close_friends'])
        self.assertTrue(check_in.is_audience(self.stranger))
        self.assertTrue(check_in.is_audience(self.friend))
        self.assertTrue(check_in.is_audience(self.close_friend))

    def test_friends_visibility(self):
        check_in = self.create_check_in(['friends'])
        self.assertFalse(check_in.is_audience(self.stranger))
        self.assertTrue(check_in.is_audience(self.friend))
        self.assertTrue(check_in.is_audience(self.close_friend)) # Close Friend is also a Friend (is_connected=True)

    def test_close_friends_visibility(self):
        check_in = self.create_check_in(['close_friends'])
        self.assertFalse(check_in.is_audience(self.stranger))
        self.assertFalse(check_in.is_audience(self.friend))
        self.assertTrue(check_in.is_audience(self.close_friend))

    def test_visibility_validation(self):
        from check_in.serializers import MyCheckInSerializer
        # Test empty visibility (NOW VALID - defaults to previous or default list)
        data = {
            'is_active': True,
            'visibility': [],
            'description': 'test'
        }
        serializer = MyCheckInSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        
        # Test valid visibility
        data['visibility'] = ['public']
        serializer = MyCheckInSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_missing_visibility_key(self):
        from check_in.serializers import MyCheckInSerializer
        # Test completely missing visibility key (NOW VALID)
        data = {
            'is_active': True,
            'description': 'test no visibility'
        }
        serializer = MyCheckInSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_create_default_visibility_initial(self):
        # Ensure no previous check-ins
        CheckIn.objects.filter(user=self.author).delete()
        
        url = reverse('current-check-in')
        data = {
            'description': 'Initial check-in',
            'visibility': []
        }
        self.client.force_authenticate(user=self.author)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        check_in = CheckIn.objects.get(id=response.data['id'])
        self.assertEqual(check_in.visibility, ['public'])

    def test_create_default_visibility_subsequent(self):
        # Create a previous check-in with specific visibility
        CheckIn.objects.create(user=self.author, visibility=['friends'], description="Previous")
        
        url = reverse('current-check-in')
        data = {
            'description': 'Subsequent check-in',
            'visibility': []
        }
        self.client.force_authenticate(user=self.author)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        check_in = CheckIn.objects.get(id=response.data['id'])
        self.assertEqual(check_in.visibility, ['friends'])

