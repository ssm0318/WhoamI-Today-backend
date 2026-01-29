from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from check_in.models import CheckIn
from account.models import Connection, Follow

User = get_user_model()

class SongListTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='current_user', email='current@test.com', password='password')
        self.friend = User.objects.create_user(username='friend', email='friend@test.com', password='password')
        self.close_friend = User.objects.create_user(username='close_friend', email='close@test.com', password='password')
        self.followed_user = User.objects.create_user(username='followed', email='followed@test.com', password='password')
        self.stranger = User.objects.create_user(username='stranger', email='stranger@test.com', password='password')
        
        # Mutual Friend User (Friend of Friend)
        self.mutual_friend = User.objects.create_user(username='mutual', email='mutual@test.com', password='password')

        self.client.force_authenticate(user=self.user)

        # Setup relationships
        # User <-> Friend
        Connection.objects.create(user1=self.user, user2=self.friend, user1_choice='friend', user2_choice='friend')
        # User <-> Close Friend
        Connection.objects.create(user1=self.user, user2=self.close_friend, user1_choice='close_friend', user2_choice='friend')
        # User -> Followed
        Follow.objects.create(follower=self.user, followed=self.followed_user)
        # Friend <-> Mutual Friend
        Connection.objects.create(user1=self.friend, user2=self.mutual_friend, user1_choice='friend', user2_choice='friend')

        # Create CheckIns with songs (within 7 days)
        # Ensure is_active=True and visibility allows viewing
        common_defaults = {'is_active': True, 'visibility': ['public', 'friends']}
        
        self.user_song = CheckIn.objects.create(user=self.user, track_id='user_song', **common_defaults)
        self.friend_song = CheckIn.objects.create(user=self.friend, track_id='friend_song', **common_defaults)
        self.close_friend_song = CheckIn.objects.create(user=self.close_friend, track_id='close_friend_song', **common_defaults)
        self.followed_song = CheckIn.objects.create(user=self.followed_user, track_id='followed_song', **common_defaults)
        self.stranger_song = CheckIn.objects.create(user=self.stranger, track_id='stranger_song', **common_defaults)
        self.mutual_song = CheckIn.objects.create(user=self.mutual_friend, track_id='mutual_song', **common_defaults)

        # Old song (older than 7 days)
        old_time = timezone.now() - timedelta(days=8)
        self.old_song = CheckIn.objects.create(user=self.user, track_id='old_song', is_active=True, visibility=['public'])
        CheckIn.objects.filter(pk=self.old_song.pk).update(created_at=old_time) # Force update created_at

    def test_list_songs_friends(self):
        """Test type='friends' (Connected users + Self)"""
        response = self.client.get('/api/playlist/feed/?type=friends')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['results'] if 'results' in response.data else response.data
        track_ids = [s['track_id'] for s in data]
        
        self.assertIn('user_song', track_ids)
        self.assertIn('friend_song', track_ids)
        self.assertIn('close_friend_song', track_ids)
        
        # Followed/Stranger/Mutual should NOT be in 'friends' list unless connected
        self.assertNotIn('followed_song', track_ids)
        self.assertNotIn('stranger_song', track_ids)
        self.assertNotIn('mutual_song', track_ids)
        self.assertNotIn('old_song', track_ids)

    def test_list_songs_default_mix(self):
        """Test default behavior (Daily Digest: Mutuals, Strangers, etc. - limit 10)"""
        # Create more dummy check-ins to test limit if needed, 
        # but here we have < 10, so it should return all suitable discovery items.
        response = self.client.get('/api/playlist/feed/') # No type param
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['results'] if 'results' in response.data else response.data
        track_ids = [s['track_id'] for s in data]

        # Should NOT contain direct friends
        self.assertNotIn('user_song', track_ids)
        self.assertNotIn('friend_song', track_ids)
        self.assertNotIn('close_friend_song', track_ids)
        
        # Should contain discovery items
        self.assertIn('mutual_song', track_ids)   
        self.assertIn('stranger_song', track_ids)
        # Followed users (who are not friends) are also valid candidates for discovery/digest
        # (matching DiscoverFeed logic which includes 'Following' category)
        self.assertIn('followed_song', track_ids)
        
        # Max limit check (2 discovery + 1 followed = 3)
        self.assertEqual(len(track_ids), 3)
        
    def test_list_songs_mutual_friends(self):
        """Test type='mutual_friends'"""
        response = self.client.get('/api/playlist/feed/?type=mutual_friends')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['results'] if 'results' in response.data else response.data
        track_ids = [s['track_id'] for s in data]
        
        self.assertIn('mutual_song', track_ids)
        self.assertNotIn('stranger_song', track_ids)
        self.assertNotIn('friend_song', track_ids)

    def test_list_songs_anonymous(self):
        """Test type='anonymous'"""
        response = self.client.get('/api/playlist/feed/?type=anonymous')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['results'] if 'results' in response.data else response.data
        track_ids = [s['track_id'] for s in data]
        
        self.assertIn('stranger_song', track_ids)
        self.assertNotIn('mutual_song', track_ids)
