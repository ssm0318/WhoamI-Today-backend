from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from check_in.models import CheckIn, Song

User = get_user_model()


class CheckInTrackIdTests(APITestCase):
    """
    CheckIn responses surface the user's active song's track_id via a
    read-only SerializerMethodField, even though Song is a separate model.
    POSTing track_id is silently ignored (it must be saved via /check_in/song/).
    """

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@test.com', password='password')
        self.client.force_authenticate(user=self.user)
        self.url = reverse('current-check-in')

    def test_create_check_in_returns_empty_track_id_when_no_song(self):
        data = {'mood': ['😎'], 'social_battery': 'fully_charged', 'visibility': ['public']}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['track_id'], '')

    def test_check_in_response_includes_active_song_track_id(self):
        CheckIn.objects.create(user=self.user, is_active=True)
        Song.objects.create(user=self.user, track_id='spotify:track:active', is_active=True)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['track_id'], 'spotify:track:active')

    def test_check_in_response_track_id_empty_when_song_inactive(self):
        CheckIn.objects.create(user=self.user, is_active=True)
        Song.objects.create(user=self.user, track_id='spotify:track:old', is_active=False)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['track_id'], '')

    def test_post_track_id_is_ignored(self):
        # Backend should not persist track_id sent via /check_in/ — it must use /check_in/song/.
        data = {'mood': ['😎'], 'visibility': ['public'], 'track_id': 'spotify:track:should-be-ignored'}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # No active song was created on the side
        self.assertEqual(response.data['track_id'], '')
        self.assertFalse(Song.objects.filter(user=self.user).exists())

    def test_post_updates_existing_active_check_in(self):
        """POST to /check_in/ updates the existing active check-in in place."""
        data1 = {'mood': ['😎'], 'visibility': ['public']}
        resp1 = self.client.post(self.url, data1, format='json')
        first_id = resp1.data['id']

        data2 = {'mood': ['🥳'], 'visibility': ['public']}
        resp2 = self.client.post(self.url, data2, format='json')

        # Same check-in is updated, not a new one created
        self.assertEqual(resp2.data['id'], first_id)
        active = CheckIn.objects.filter(user=self.user, is_active=True)
        self.assertEqual(active.count(), 1)


class SongCRUDTests(APITestCase):
    """Song CRUD with active/inactive pattern."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@test.com', password='password')
        self.client.force_authenticate(user=self.user)
        self.list_url = reverse('current-song')

    def test_create_song(self):
        data = {'track_id': 'spotify:track:abc123'}
        response = self.client.post(self.list_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['track_id'], 'spotify:track:abc123')
        self.assertTrue(response.data['is_active'])

    def test_get_active_song(self):
        Song.objects.create(user=self.user, track_id='track1', is_active=True)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results'] if 'results' in response.data else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['track_id'], 'track1')

    def test_create_song_deactivates_previous(self):
        data1 = {'track_id': 'track_old'}
        resp1 = self.client.post(self.list_url, data1, format='json')
        old_id = resp1.data['id']

        data2 = {'track_id': 'track_new'}
        self.client.post(self.list_url, data2, format='json')

        old_song = Song.objects.get(id=old_id)
        self.assertFalse(old_song.is_active)

        active = Song.objects.filter(user=self.user, is_active=True)
        self.assertEqual(active.count(), 1)
        self.assertEqual(active.first().track_id, 'track_new')

    def test_delete_song_deactivates(self):
        song = Song.objects.create(user=self.user, track_id='track1', is_active=True)
        detail_url = reverse('my-song-detail', kwargs={'pk': song.pk})
        response = self.client.patch(detail_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_active'])

        active = Song.objects.filter(user=self.user, is_active=True)
        self.assertEqual(active.count(), 0)

    def test_no_active_song_returns_empty(self):
        response = self.client.get(self.list_url)
        results = response.data['results'] if 'results' in response.data else response.data
        self.assertEqual(len(results), 0)

    def test_other_user_cannot_access_song(self):
        other = User.objects.create_user(username='other', email='other@test.com', password='password')
        song = Song.objects.create(user=other, track_id='secret', is_active=True)
        detail_url = reverse('my-song-detail', kwargs={'pk': song.pk})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class LatestCheckInTests(APITestCase):
    """GET /api/check_in/latest/ returns most recent check-in regardless of is_active."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@test.com', password='password')
        self.client.force_authenticate(user=self.user)
        self.url = reverse('latest-check-in')

    def test_no_check_ins_returns_empty(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {})

    def test_returns_latest_even_if_inactive(self):
        CheckIn.objects.create(user=self.user, is_active=False, thought='old inactive')
        latest = CheckIn.objects.create(user=self.user, is_active=False, thought='latest inactive')

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], latest.id)

    def test_returns_active_if_exists(self):
        CheckIn.objects.create(user=self.user, is_active=False, thought='inactive')
        active = CheckIn.objects.create(user=self.user, is_active=True, thought='active one')

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], active.id)


class CheckInExpiryTests(APITestCase):
    """Test that the cron job expires check-ins after 12 hours."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@test.com', password='password')

    def test_expire_old_check_ins(self):
        from check_in.cron import ExpireCheckInsCronJob

        # Create a check-in older than 12 hours
        old = CheckIn.objects.create(user=self.user, is_active=True, thought='old')
        CheckIn.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=13))

        # Create a fresh check-in
        fresh = CheckIn.objects.create(user=self.user, is_active=True, thought='fresh')

        # Run cron
        job = ExpireCheckInsCronJob()
        job.do()

        old.refresh_from_db()
        fresh.refresh_from_db()
        self.assertFalse(old.is_active)
        self.assertTrue(fresh.is_active)
