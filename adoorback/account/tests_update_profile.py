from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse
from notification.models import Notification, NotificationActor
from django.contrib.contenttypes.models import ContentType

User = get_user_model()

class UserProfileUpdateTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='old_username', email='test@example.com', password='password')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = reverse('current-user-detail')

    def test_username_update_success(self):
        # Create a notification that should be updated
        # Assuming there is a notification related to friendship
        # The logic filters friendship_originated_notis with target_type=User
        
        # We need another user to be the target or involved
        other_user = User.objects.create_user(username='friend', email='friend@example.com', password='password')
        
        # Create a notification where 'user' is the actor (origin) 
        # and it is a friendship notification (target is User)
        # Note: friendship_originated_notis means notification.origin = user
        user_ct = ContentType.objects.get_for_model(User)
        
        noti = Notification.objects.create(
            user=other_user, # The receiver of notification
            origin_id=self.user.id,
            origin_type=user_ct,
            target_id=other_user.id, # Target is the other user (e.g. "became friends with X")
            target_type=user_ct,
            message_ko="Test Noti",
            message_en="Test Noti",
            redirect_url=f"/users/{self.user.username}"
        )
        NotificationActor.objects.create(user=self.user, notification=noti)
        
        # Action: Update username
        new_username = 'new_username'
        data = {'username': new_username}
        response = self.client.patch(self.url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, new_username)
        
        # Check if notification redirect_url is updated
        noti.refresh_from_db()
        expected_url = f"/users/{new_username}"
        self.assertEqual(noti.redirect_url, expected_url)
