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

    def test_profile_visibility_update_and_view(self):
        # User updates visibility preferences to 'friends' (per-field 4-way enum)
        update_data = {
            'bio_visibility': 'friends',
            'pronouns_visibility': 'friends',
            'music_entertainment_visibility': 'friends',
            'hobbies_activities_visibility': 'friends',
            'on_my_mind_visibility': 'friends',
            'as_a_friend_visibility': 'friends',
            'online_persona_visibility': 'friends',
            'favorite_platform_visibility': 'friends',
            'least_favorite_platform_visibility': 'friends',
            'bio': 'My secret bio',
            'pronouns': 'they/them'
        }
        res = self.client.patch(self.url, update_data)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertEqual(self.user.bio_visibility, 'friends')
        self.assertEqual(self.user.online_persona_visibility, 'friends')
        self.assertEqual(self.user.bio, 'My secret bio')

        # Another user, not friends, views the profile
        other_user = User.objects.create_user(username='viewer', email='viewer@example.com', password='password')
        other_client = APIClient()
        other_client.force_authenticate(user=other_user)

        profile_url = reverse('user-detail', kwargs={'username': self.user.username})
        res = other_client.get(profile_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Verify fields are hidden
        self.assertIsNone(res.data.get('bio'))
        self.assertIsNone(res.data.get('pronouns'))
        self.assertEqual(res.data.get('user_interests'), [])
        self.assertEqual(res.data.get('persona'), [])
        self.assertEqual(res.data.get('user_personas'), [])

        # The two users become friends
        from account.models import Connection
        Connection.objects.create(user1=self.user, user2=other_user, user1_choice='friend', user2_choice='friend')

        # The other user views the profile again
        res = other_client.get(profile_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        
        # Verify fields are now visible
        self.assertEqual(res.data.get('bio'), 'My secret bio')
        self.assertEqual(res.data.get('pronouns'), 'they/them')
