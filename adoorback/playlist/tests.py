from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from playlist.models import Song
from account.models import Connection, Follow

User = get_user_model()

class SongListTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='current_user', email='current@test.com', password='password')
        self.friend = User.objects.create_user(username='friend', email='friend@test.com', password='password')
        self.close_friend = User.objects.create_user(username='close_friend', email='close@test.com', password='password')
        self.followed_user = User.objects.create_user(username='followed', email='followed@test.com', password='password')
        self.stranger = User.objects.create_user(username='stranger', email='stranger@test.com', password='password')

        self.client.force_authenticate(user=self.user)

        # Setup relationships
        Connection.objects.create(user1=self.user, user2=self.friend, user1_choice='friend', user2_choice='friend')
        Connection.objects.create(user1=self.user, user2=self.close_friend, user1_choice='close_friend', user2_choice='friend')
        Follow.objects.create(follower=self.user, followed=self.followed_user)

        # Create songs (within 7 days)
        self.user_song = Song.objects.create(user=self.user, track_id='user_song')
        self.friend_song = Song.objects.create(user=self.friend, track_id='friend_song')
        self.close_friend_song = Song.objects.create(user=self.close_friend, track_id='close_friend_song')
        self.followed_song = Song.objects.create(user=self.followed_user, track_id='followed_song')
        self.stranger_song = Song.objects.create(user=self.stranger, track_id='stranger_song')

        # Old song (older than 7 days)
        old_time = timezone.now() - timedelta(days=8)
        self.old_song = Song.objects.create(user=self.user, track_id='old_song')
        self.old_song.created_at = old_time
        self.old_song.save()

    def test_list_songs_default(self):
        """Test default behavior (friends + close friends + self)"""
        response = self.client.get('/api/playlist/feed/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['results'] if 'results' in response.data else response.data
        track_ids = [s['track_id'] for s in data]
        
        self.assertIn('user_song', track_ids)
        self.assertIn('friend_song', track_ids)
        self.assertIn('close_friend_song', track_ids)
        self.assertNotIn('followed_song', track_ids)
        self.assertNotIn('stranger_song', track_ids)
        self.assertNotIn('old_song', track_ids)

    def test_list_songs_friends(self):
        """Test type='friends' (same as default)"""
        response = self.client.get('/api/playlist/feed/?type=friends')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['results'] if 'results' in response.data else response.data
        track_ids = [s['track_id'] for s in data]
        
        self.assertIn('user_song', track_ids)
        self.assertIn('friend_song', track_ids)
        self.assertIn('close_friend_song', track_ids)
        self.assertNotIn('followed_song', track_ids)
        self.assertNotIn('stranger_song', track_ids)
        self.assertNotIn('old_song', track_ids)

    def test_list_songs_close_friends(self):
        """Test type='close_friends' (close friends + self)"""
        response = self.client.get('/api/playlist/feed/?type=close_friends')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['results'] if 'results' in response.data else response.data
        track_ids = [s['track_id'] for s in data]
        
        self.assertIn('user_song', track_ids)
        self.assertNotIn('friend_song', track_ids)
        self.assertIn('close_friend_song', track_ids)
        self.assertNotIn('followed_song', track_ids)
        self.assertNotIn('stranger_song', track_ids)

    def test_list_songs_following(self):
        """Test type='following' (following + self)"""
        response = self.client.get('/api/playlist/feed/?type=following')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['results'] if 'results' in response.data else response.data
        track_ids = [s['track_id'] for s in data]
        
        self.assertIn('user_song', track_ids)
        self.assertNotIn('friend_song', track_ids)
        self.assertNotIn('close_friend_song', track_ids)  # Unless followed, but here strictly checking following relation
        self.assertIn('followed_song', track_ids)
        self.assertNotIn('stranger_song', track_ids)
