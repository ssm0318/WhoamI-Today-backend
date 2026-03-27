from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from check_in.models import Song
from account.models import Connection
from playlist.models import PlaylistFeed

User = get_user_model()


class PlaylistFeedTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='current_user', email='current@test.com', password='password')
        self.friend = User.objects.create_user(username='friend', email='friend@test.com', password='password')
        self.close_friend = User.objects.create_user(username='close_friend', email='close@test.com', password='password')
        self.stranger = User.objects.create_user(username='stranger', email='stranger@test.com', password='password')
        self.mutual_friend = User.objects.create_user(username='mutual', email='mutual@test.com', password='password')

        self.client.force_authenticate(user=self.user)

        # User <-> Friend
        Connection.objects.create(user1=self.user, user2=self.friend, user1_choice='friend', user2_choice='friend')
        # User <-> Close Friend
        Connection.objects.create(user1=self.user, user2=self.close_friend, user1_choice='close_friend', user2_choice='friend')
        # Friend <-> Mutual Friend (makes mutual_friend a "mutual friend" of user)
        Connection.objects.create(user1=self.friend, user2=self.mutual_friend, user1_choice='friend', user2_choice='friend')

        # Create active songs (friends/close_friends excluded from discover feed)
        Song.objects.create(user=self.stranger, track_id='stranger_song', is_active=True)
        Song.objects.create(user=self.mutual_friend, track_id='mutual_song', is_active=True)

        PlaylistFeed.objects.all().delete()

    def test_default_feed_generates_daily_digest(self):
        """Default request generates a daily digest."""
        response = self.client.get('/api/playlist/feed/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['results'] if 'results' in response.data else response.data
        track_ids = [s['track_id'] for s in data]

        self.assertIn('mutual_song', track_ids)
        self.assertIn('stranger_song', track_ids)

    def test_default_feed_is_persistent(self):
        """Same feed returned within the same day."""
        resp1 = self.client.get('/api/playlist/feed/')
        data1 = resp1.data['results'] if 'results' in resp1.data else resp1.data
        ids1 = [s['track_id'] for s in data1]

        # Add new song — should NOT appear in today's feed
        new_user = User.objects.create_user(username='newcomer', email='new@test.com', password='password')
        Song.objects.create(user=new_user, track_id='new_song', is_active=True)

        resp2 = self.client.get('/api/playlist/feed/')
        data2 = resp2.data['results'] if 'results' in resp2.data else resp2.data
        ids2 = [s['track_id'] for s in data2]

        self.assertEqual(ids1, ids2)
        self.assertNotIn('new_song', ids2)

    def test_filter_mutual_friends(self):
        """?type=mutual_friends returns only mutual_friends from daily digest."""
        # Generate the digest first
        self.client.get('/api/playlist/feed/')

        response = self.client.get('/api/playlist/feed/?type=mutual_friends')
        data = response.data['results'] if 'results' in response.data else response.data
        track_ids = [s['track_id'] for s in data]

        self.assertIn('mutual_song', track_ids)
        self.assertNotIn('stranger_song', track_ids)

    def test_filter_mutual_traits(self):
        """?type=mutual_traits returns only mutual_traits from daily digest."""
        self.client.get('/api/playlist/feed/')

        response = self.client.get('/api/playlist/feed/?type=mutual_traits')
        data = response.data['results'] if 'results' in response.data else response.data
        # No mutual_traits songs set up, so should be empty
        self.assertEqual(len(data), 0)

    def test_filter_combined(self):
        """?type=mutual_friends,mutual_traits returns both categories."""
        self.client.get('/api/playlist/feed/')

        response = self.client.get('/api/playlist/feed/?type=mutual_friends,mutual_traits')
        data = response.data['results'] if 'results' in response.data else response.data
        track_ids = [s['track_id'] for s in data]

        # mutual_song is categorized as mutual_friends
        self.assertIn('mutual_song', track_ids)

    def test_filter_is_subset_of_digest(self):
        """Filtered results should be a subset of the full digest."""
        resp_all = self.client.get('/api/playlist/feed/')
        data_all = resp_all.data['results'] if 'results' in resp_all.data else resp_all.data
        all_ids = {s['id'] for s in data_all}

        resp_mf = self.client.get('/api/playlist/feed/?type=mutual_friends')
        data_mf = resp_mf.data['results'] if 'results' in resp_mf.data else resp_mf.data
        mf_ids = {s['id'] for s in data_mf}

        self.assertTrue(mf_ids.issubset(all_ids))

    def test_inactive_songs_excluded(self):
        """Inactive songs should not appear in the feed."""
        Song.objects.filter(track_id='stranger_song').update(is_active=False)

        response = self.client.get('/api/playlist/feed/')
        data = response.data['results'] if 'results' in response.data else response.data
        track_ids = [s['track_id'] for s in data]

        self.assertNotIn('stranger_song', track_ids)
