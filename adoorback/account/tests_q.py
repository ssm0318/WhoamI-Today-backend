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

    def test_q_me_excludes_friends_only_fields(self):
        """Q me should NOT include per-item *_friends_only fields (Q uses is_public)."""
        url = reverse('q-current-user-detail')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('interests_friends_only', response.data)
        self.assertNotIn('persona_friends_only', response.data)
        self.assertNotIn('pronouns_friends_only', response.data)
        self.assertNotIn('bio_friends_only', response.data)
        self.assertNotIn('music_entertainment_friends_only', response.data)
        # is_public should still be present
        self.assertIn('is_public', response.data)

    def test_q_me_still_has_interests_and_personas(self):
        """Q me should have user_interests and user_personas as flat lists."""
        url = reverse('q-current-user-detail')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('user_interests', response.data)
        self.assertIn('user_personas', response.data)


class QPublicPrivateProfileTests(APITestCase):
    """Test is_public-based profile visibility for Ver.Q."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='viewer', email='viewer@test.com', password='password',
            current_ver='version_q'
        )
        self.target = User.objects.create_user(
            username='target', email='target@test.com', password='password',
            current_ver='version_q', bio='My bio', pronouns='they/them'
        )
        self.client.force_authenticate(user=self.user)

    def test_public_account_shows_bio_to_non_friends(self):
        self.target.is_public = True
        self.target.save()
        url = reverse('q-user-detail', kwargs={'username': 'target'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('bio'), 'My bio')
        self.assertEqual(response.data.get('pronouns'), 'they/them')

    def test_private_account_hides_bio_from_non_friends(self):
        self.target.is_public = False
        self.target.save()
        url = reverse('q-user-detail', kwargs={'username': 'target'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data.get('bio'))
        self.assertIsNone(response.data.get('pronouns'))
        self.assertEqual(response.data.get('user_interests'), [])
        self.assertEqual(response.data.get('user_personas'), [])

    def test_private_account_shows_bio_to_friends(self):
        self.target.is_public = False
        self.target.save()
        Connection.objects.create(
            user1=self.user, user2=self.target,
            user1_choice='friend', user2_choice='friend'
        )
        url = reverse('q-user-detail', kwargs={'username': 'target'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('bio'), 'My bio')
        self.assertEqual(response.data.get('pronouns'), 'they/them')

    def test_public_account_ignores_stale_friends_only_flags(self):
        """Even if stale *_friends_only flags are True, public Q account shows everything."""
        self.target.is_public = True
        self.target.bio_friends_only = True
        self.target.pronouns_friends_only = True
        self.target.save()
        url = reverse('q-user-detail', kwargs={'username': 'target'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('bio'), 'My bio')
        self.assertEqual(response.data.get('pronouns'), 'they/them')


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


class QDiscoverFeedTests(APITestCase):
    """Test Version Q /api/q/user/discover/ endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', email='test@test.com', password='password',
            current_ver='version_q', user_group='group_q_first'
        )
        self.friend = User.objects.create_user(
            username='friend', email='friend@test.com', password='password',
            current_ver='version_q'
        )
        self.stranger = User.objects.create_user(
            username='stranger', email='stranger@test.com', password='password',
            current_ver='version_q'
        )
        self.stranger2 = User.objects.create_user(
            username='stranger2', email='stranger2@test.com', password='password',
            current_ver='version_q'
        )
        self.user_w = User.objects.create_user(
            username='user_w', email='w@test.com', password='password',
            current_ver='version_w'
        )
        self.blocked_user = User.objects.create_user(
            username='blocked', email='blocked@test.com', password='password',
            current_ver='version_q'
        )
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password'
        )

        # Create friendship
        Connection.objects.create(
            user1=self.user, user2=self.friend,
            user1_choice='friend', user2_choice='friend'
        )

        # Create block
        from user_report.models import UserReport
        UserReport.objects.create(user=self.user, reported_user=self.blocked_user)

        # Create a question for responses
        self.question = Question.objects.create(
            author=self.admin, content='Test question?'
        )

        # Public posts from stranger (should appear)
        self.stranger_note = Note.objects.create(
            author=self.stranger, content='Stranger public note',
            visibility=['public']
        )
        self.stranger_response = Response.objects.create(
            author=self.stranger, question=self.question,
            content='Stranger public response', visibility=['public']
        )

        # Public post from friend (should NOT appear)
        Note.objects.create(
            author=self.friend, content='Friend public note',
            visibility=['public']
        )

        # Non-public post from stranger (should NOT appear)
        Note.objects.create(
            author=self.stranger, content='Stranger private note',
            visibility=['friends']
        )

        # Public post from blocked user (should NOT appear)
        Note.objects.create(
            author=self.blocked_user, content='Blocked user note',
            visibility=['public']
        )

        # Public post from ver.w user (should NOT appear)
        Note.objects.create(
            author=self.user_w, content='Other version note',
            visibility=['public']
        )

        # Public post from superuser (should NOT appear)
        Note.objects.create(
            author=self.admin, content='Admin note',
            visibility=['public']
        )

        self.client.force_authenticate(user=self.user)
        self.url = reverse('q-discover-feed')

    def test_returns_public_posts_from_non_friends(self):
        """Discover should return public posts from non-friends only."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        authors = [item['body']['author_detail']['username'] for item in results]
        self.assertIn('stranger', authors)
        self.assertNotIn('friend', authors)

    def test_excludes_blocked_users(self):
        """Discover should exclude posts from blocked users."""
        response = self.client.get(self.url)
        results = response.data.get('results', response.data)
        authors = [item['body']['author_detail']['username'] for item in results]
        self.assertNotIn('blocked', authors)

    def test_excludes_other_version(self):
        """Discover should exclude posts from users on different version."""
        response = self.client.get(self.url)
        results = response.data.get('results', response.data)
        authors = [item['body']['author_detail']['username'] for item in results]
        self.assertNotIn('user_w', authors)

    def test_excludes_superusers(self):
        """Discover should exclude posts from superusers."""
        response = self.client.get(self.url)
        results = response.data.get('results', response.data)
        authors = [item['body']['author_detail']['username'] for item in results]
        self.assertNotIn('admin', authors)

    def test_excludes_non_public_posts(self):
        """Discover should only return posts with public visibility."""
        response = self.client.get(self.url)
        results = response.data.get('results', response.data)
        contents = [item['body']['content'] for item in results]
        self.assertNotIn('Stranger private note', contents)

    def test_returns_both_notes_and_responses(self):
        """Discover should return both Note and Response types."""
        response = self.client.get(self.url)
        results = response.data.get('results', response.data)
        types = [item['type'] for item in results]
        self.assertIn('Note', types)
        self.assertIn('Response', types)

    def test_wrapper_format(self):
        """Each item should have type and body keys."""
        response = self.client.get(self.url)
        results = response.data.get('results', response.data)
        for item in results:
            self.assertIn('type', item)
            self.assertIn('body', item)
            self.assertIn(item['type'], ['Note', 'Response'])

    def test_reverse_chronological_order(self):
        """Posts should be ordered newest first."""
        # Create a newer post from stranger2
        Note.objects.create(
            author=self.stranger2, content='Newer note',
            visibility=['public']
        )
        response = self.client.get(self.url)
        results = response.data.get('results', response.data)
        timestamps = [item['body']['created_at'] for item in results]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))

    def test_marks_as_read(self):
        """Fetching discover should mark posts as read."""
        self.assertFalse(self.user.read_notes.filter(id=self.stranger_note.id).exists())
        self.assertFalse(self.user.read_responses.filter(id=self.stranger_response.id).exists())

        self.client.get(self.url)

        self.assertTrue(self.user.read_notes.filter(id=self.stranger_note.id).exists())
        self.assertTrue(self.user.read_responses.filter(id=self.stranger_response.id).exists())

    def test_uses_q_serializers(self):
        """Discover should use Q serializers (no share_type, no reactions)."""
        response = self.client.get(self.url)
        results = response.data.get('results', response.data)
        for item in results:
            self.assertNotIn('share_type', item['body'])
            self.assertNotIn('current_user_reaction_id_list', item['body'])
            self.assertIn('like_count', item['body'])


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
