from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from check_in.models import CheckIn, Song

User = get_user_model()


class CheckInWithoutTrackIdTests(APITestCase):
    """CheckIn should no longer accept or return track_id."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@test.com', password='password')
        self.client.force_authenticate(user=self.user)
        self.url = reverse('current-check-in')

    def test_create_check_in_without_track_id(self):
        data = {'mood': '😎', 'social_battery': 'fully_charged', 'description': 'no song'}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn('track_id', response.data)

    def test_check_in_response_has_no_track_id(self):
        CheckIn.objects.create(user=self.user, is_active=True, description='test')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data['results']:
            self.assertNotIn('track_id', item)

    def test_create_check_in_deactivates_previous(self):
        data1 = {'mood': '😎', 'description': 'first'}
        resp1 = self.client.post(self.url, data1, format='json')
        first_id = resp1.data['id']

        data2 = {'mood': '🥳', 'description': 'second'}
        self.client.post(self.url, data2, format='json')

        first = CheckIn.objects.get(id=first_id)
        self.assertFalse(first.is_active)

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
        CheckIn.objects.create(user=self.user, is_active=False, description='old inactive')
        CheckIn.objects.create(user=self.user, is_active=False, mood='🥳', description='latest inactive')

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['description'], 'latest inactive')
        self.assertEqual(response.data['mood'], '🥳')

    def test_returns_active_if_exists(self):
        CheckIn.objects.create(user=self.user, is_active=False, description='inactive')
        CheckIn.objects.create(user=self.user, is_active=True, description='active one')

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['description'], 'active one')


class CheckInExpiryTests(APITestCase):
    """Test that the cron job expires check-ins after 12 hours."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@test.com', password='password')

    def test_expire_old_check_ins(self):
        from check_in.cron import ExpireCheckInsCronJob

        # Create a check-in older than 12 hours
        old = CheckIn.objects.create(user=self.user, is_active=True, description='old')
        CheckIn.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=13))

        # Create a fresh check-in
        fresh = CheckIn.objects.create(user=self.user, is_active=True, description='fresh')

        # Run cron
        job = ExpireCheckInsCronJob()
        job.do()

        old.refresh_from_db()
        fresh.refresh_from_db()
        self.assertFalse(old.is_active)
        self.assertTrue(fresh.is_active)
