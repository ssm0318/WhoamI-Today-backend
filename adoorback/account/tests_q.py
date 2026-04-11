from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse

from account.models import Connection
from note.models import Note
from qna.models import Question, Response

User = get_user_model()


class QCurrentUserTests(APITestCase):
    """Test Version Q /api/q/user/me/ endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', email='test@test.com', password='password',
            current_ver='version_q', user_group='group_q_first'
        )
        self.client.force_authenticate(user=self.user)

    def test_q_me_excludes_chip_fields(self):
        """Q me endpoint should not include chips_by_category or custom_chips."""
        url = reverse('q-current-user-detail')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('chips_by_category', response.data)
        self.assertNotIn('custom_chips', response.data)
        # Basic fields should still be present
        self.assertIn('username', response.data)
        self.assertIn('current_ver', response.data)
        self.assertEqual(response.data['current_ver'], 'version_q')

    def test_w_me_includes_chip_fields(self):
        """W me endpoint should include chips_by_category and custom_chips."""
        url = reverse('current-user-detail')  # W endpoint
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('chips_by_category', response.data)
        self.assertIn('custom_chips', response.data)

    def test_q_me_includes_privacy_fields(self):
        """Q me should still include privacy fields (same as W)."""
        url = reverse('q-current-user-detail')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('interests_friends_only', response.data)
        self.assertIn('persona_friends_only', response.data)

    def test_q_me_still_has_interests_and_personas(self):
        """Q me should have user_interests and user_personas as flat lists."""
        url = reverse('q-current-user-detail')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('user_interests', response.data)
        self.assertIn('user_personas', response.data)


class QUserProfileTests(APITestCase):
    """Test Version Q /api/q/user/<username>/profile/ endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='viewer', email='viewer@test.com', password='password',
            current_ver='version_q'
        )
        self.target = User.objects.create_user(
            username='target', email='target@test.com', password='password',
            current_ver='version_q'
        )
        Connection.objects.create(
            user1=self.user, user2=self.target,
            user1_choice='friend', user2_choice='friend'
        )
        self.client.force_authenticate(user=self.user)

    def test_q_profile_excludes_chip_fields(self):
        """Q profile should not include chip-related or friendship_level fields."""
        url = reverse('q-user-detail', kwargs={'username': self.target.username})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('mutual_interests', response.data)
        self.assertNotIn('mutual_personas', response.data)
        self.assertNotIn('friendship_level', response.data)

    def test_w_profile_includes_chip_fields(self):
        """W profile should include mutual_interests and friendship_level."""
        url = reverse('user-detail', kwargs={'username': self.target.username})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('mutual_interests', response.data)
        self.assertIn('friendship_level', response.data)


class QFeedTests(APITestCase):
    """Test Version Q feed endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', email='test@test.com', password='password',
            current_ver='version_q'
        )
        self.friend = User.objects.create_user(
            username='friend', email='friend@test.com', password='password',
            current_ver='version_q'
        )
        Connection.objects.create(
            user1=self.user, user2=self.friend,
            user1_choice='friend', user2_choice='friend'
        )
        Note.objects.create(
            author=self.friend, content='Feed note',
            visibility=['friends']
        )
        self.client.force_authenticate(user=self.user)

    def test_q_feed_returns_notes_with_q_format(self):
        """Q feed should return notes without share_type and with likes only."""
        url = reverse('q-friend-feed')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertTrue(len(results) > 0)
        note_data = results[0]
        self.assertNotIn('share_type', note_data)
        self.assertNotIn('current_user_reaction_id_list', note_data)
        self.assertIn('like_count', note_data)


class QAllPostsTests(APITestCase):
    """Test Version Q all-posts endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', email='test@test.com', password='password',
            current_ver='version_q'
        )
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password'
        )
        Note.objects.create(
            author=self.user, content='My note',
            visibility=['friends']
        )
        question = Question.objects.create(
            author=self.admin, content='Test question?'
        )
        Response.objects.create(
            author=self.user, question=question,
            content='My answer', visibility=['friends']
        )
        self.client.force_authenticate(user=self.user)

    def test_q_all_posts_uses_q_serializers(self):
        """Q all-posts should use Q serializers for both notes and responses."""
        url = reverse('q-current-user-all-post-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 2)
        for item in results:
            self.assertNotIn('current_user_reaction_id_list', item)
            if item['type'] == 'Note':
                self.assertNotIn('share_type', item)
                self.assertIn('like_count', item)


class CrossVersionFriendRequestTests(APITestCase):
    """Test that cross-version friend requests are still blocked."""

    def setUp(self):
        self.user_w = User.objects.create_user(
            username='user_w', email='w@test.com', password='password',
            current_ver='version_w'
        )
        self.user_q = User.objects.create_user(
            username='user_q', email='q@test.com', password='password',
            current_ver='version_q'
        )
        self.client.force_authenticate(user=self.user_w)

    def test_cross_version_friend_request_blocked(self):
        """Friend request between version_w and version_q users should fail."""
        url = reverse('user-friend-request-list')
        data = {
            'requester_id': self.user_w.id,
            'requestee_id': self.user_q.id,
            'requester_choice': 'friend',
        }
        response = self.client.post(url, data)
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])

    def test_same_version_friend_request_allowed(self):
        """Friend request between same-version users should work."""
        user_w2 = User.objects.create_user(
            username='user_w2', email='w2@test.com', password='password',
            current_ver='version_w'
        )
        url = reverse('user-friend-request-list')
        data = {
            'requester_id': self.user_w.id,
            'requestee_id': user_w2.id,
            'requester_choice': 'friend',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class RemovedDefaultEndpointTests(APITestCase):
    """Test that old /default/ endpoints are gone."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', email='test@test.com', password='password'
        )
        self.client.force_authenticate(user=self.user)

    def test_default_note_list_gone(self):
        response = self.client.get('/api/user/me/notes/default/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_default_user_notes_gone(self):
        response = self.client.get('/api/user/testuser/notes/default/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_default_friend_request_gone(self):
        response = self.client.post('/api/user/friend-requests/default/', {})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_default_note_detail_gone(self):
        response = self.client.get('/api/notes/1/default/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
