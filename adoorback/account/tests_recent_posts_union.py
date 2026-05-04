"""Tests for the get_recent_posts union logic.

The serializer now returns the union of:
  - Posts created in the last 24 hours
  - Posts the viewer has NOT read yet
This replaces the old behaviour that only returned the 24-hour window.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, APITestCase

from account.models import Connection
from account.serializers import FriendListSerializer
from check_in.models import CheckIn, Song
from note.models import Note
from qna.models import Question, Response

User = get_user_model()


# ---------------------------------------------------------------------------
# Unit tests – directly exercise the serializer
# ---------------------------------------------------------------------------

class RecentPostsUnionSerializerTests(TestCase):
    """Test get_recent_posts via FriendListSerializer with manual context."""

    def setUp(self):
        self.viewer = User.objects.create_user(
            username='rp_viewer', email='rp_viewer@test.com', password='password',
        )
        self.friend = User.objects.create_user(
            username='rp_friend', email='rp_friend@test.com', password='password',
        )
        Connection.objects.create(
            user1=self.viewer, user2=self.friend,
            user1_choice='friend', user2_choice='friend',
        )
        self.question = Question.objects.create(
            author=self.friend, content='test question?', is_admin_question=False,
        )
        self.factory = APIRequestFactory()

    # -- helpers --

    def _make_context(self, notes=None, resps=None):
        """Build the minimal context dict required by FriendListSerializer."""
        request = self.factory.get('/')
        request.user = self.viewer
        return {
            'request': request,
            'favorite_ids': set(),
            'hidden_ids': set(),
            'connection_by_friend_id': {},
            'visible_check_in_by_user_id': {},
            'active_song_by_user_id': {},
            'unread_note_count_by_author': {},
            'unread_response_count_by_author': {},
            'unread_chat_count_by_friend_id': {},
            'visible_notes_by_author': {
                self.friend.id: notes or [],
            },
            'visible_resps_by_author': {
                self.friend.id: resps or [],
            },
            'pokes_by_receiver': {},
            'check_in_subscription_ids': set(),
            'subscription_ids': set(),
            'pinned_count_by_friend_id': {},
        }

    def _serialize(self, notes=None, resps=None):
        ctx = self._make_context(notes=notes, resps=resps)
        serializer = FriendListSerializer(self.friend, context=ctx)
        return serializer.data['recent_posts']

    def _create_note(self, age_hours=0, read_by_viewer=False, **kwargs):
        """Create a Note with created_at in the past by *age_hours*."""
        defaults = dict(
            author=self.friend,
            content=f'note {age_hours}h ago',
            visibility=['friends'],
        )
        defaults.update(kwargs)
        note = Note.objects.create(**defaults)
        if age_hours:
            Note.objects.filter(pk=note.pk).update(
                created_at=timezone.now() - timedelta(hours=age_hours),
            )
            note.refresh_from_db()
        if read_by_viewer:
            note.readers.add(self.viewer)
        return note

    def _create_response(self, age_hours=0, read_by_viewer=False, **kwargs):
        defaults = dict(
            author=self.friend,
            question=self.question,
            content=f'response {age_hours}h ago',
            visibility=['friends'],
        )
        defaults.update(kwargs)
        resp = Response.objects.create(**defaults)
        if age_hours:
            Response.objects.filter(pk=resp.pk).update(
                created_at=timezone.now() - timedelta(hours=age_hours),
            )
            resp.refresh_from_db()
        if read_by_viewer:
            resp.readers.add(self.viewer)
        return resp

    # -- tests --

    def test_recent_note_included(self):
        """A note created <24h ago should always appear."""
        note = self._create_note(age_hours=1)
        posts = self._serialize(notes=[note])
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]['type'], 'Note')
        self.assertEqual(posts[0]['id'], note.id)

    def test_old_unread_note_included(self):
        """A note created >24h ago but unread should appear (new union logic)."""
        note = self._create_note(age_hours=48)
        posts = self._serialize(notes=[note])
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]['id'], note.id)

    def test_old_read_note_excluded(self):
        """A note created >24h ago AND already read should NOT appear."""
        note = self._create_note(age_hours=48, read_by_viewer=True)
        posts = self._serialize(notes=[note])
        self.assertEqual(len(posts), 0)

    def test_recent_read_note_still_included(self):
        """A note created <24h ago that's already read should still appear."""
        note = self._create_note(age_hours=2, read_by_viewer=True)
        posts = self._serialize(notes=[note])
        self.assertEqual(len(posts), 1)

    def test_union_no_duplicates(self):
        """A recent AND unread note should appear exactly once (no dupe)."""
        note = self._create_note(age_hours=1)  # recent + unread
        posts = self._serialize(notes=[note])
        self.assertEqual(len(posts), 1)

    def test_mixed_notes_and_responses(self):
        """Union includes both Note and Response objects."""
        note = self._create_note(age_hours=48)  # old unread
        resp = self._create_response(age_hours=1)  # recent
        posts = self._serialize(notes=[note], resps=[resp])
        self.assertEqual(len(posts), 2)
        types = {p['type'] for p in posts}
        self.assertEqual(types, {'Note', 'Response'})

    def test_sorted_by_created_at_descending(self):
        """Results are sorted newest-first."""
        old = self._create_note(age_hours=48)  # old unread
        recent = self._create_note(age_hours=1)  # recent
        posts = self._serialize(notes=[old, recent])
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0]['id'], recent.id)
        self.assertEqual(posts[1]['id'], old.id)

    def test_empty_when_all_old_and_read(self):
        """No posts returned when everything is old AND read."""
        self._create_note(age_hours=48, read_by_viewer=True)
        self._create_response(age_hours=72, read_by_viewer=True)
        posts = self._serialize(
            notes=[Note.objects.get(author=self.friend)],
            resps=[Response.objects.get(author=self.friend)],
        )
        # Re-fetch to get the reader state
        note = Note.objects.get(author=self.friend)
        resp = Response.objects.get(author=self.friend)
        posts = self._serialize(notes=[note], resps=[resp])
        self.assertEqual(len(posts), 0)

    def test_empty_lists(self):
        """No crash when there are no visible posts at all."""
        posts = self._serialize(notes=[], resps=[])
        self.assertEqual(len(posts), 0)

    def test_old_unread_response_included(self):
        """Responses also benefit from the union logic."""
        resp = self._create_response(age_hours=72)
        posts = self._serialize(resps=[resp])
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]['type'], 'Response')


# ---------------------------------------------------------------------------
# Integration tests – hit the /api/user/friends/ endpoint
# ---------------------------------------------------------------------------

class FriendsListRecentPostsIntegrationTests(APITestCase):
    """Test get_recent_posts union through the actual API endpoint."""

    URL = '/api/user/friends/'

    def setUp(self):
        self.viewer = User.objects.create_user(
            username='fl_viewer', email='fl_viewer@test.com', password='password',
        )
        self.friend = User.objects.create_user(
            username='fl_friend', email='fl_friend@test.com', password='password',
        )
        Connection.objects.create(
            user1=self.viewer, user2=self.friend,
            user1_choice='friend', user2_choice='friend',
        )
        self.question = Question.objects.create(
            author=self.friend, content='test q?', is_admin_question=False,
        )
        self.client.force_authenticate(user=self.viewer)

    def _get_friend_data(self):
        """Fetch the friends list and return the first friend's data."""
        response = self.client.get(self.URL, {'type': 'all'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', [])
        for friend in results:
            if friend['username'] == self.friend.username:
                return friend
        self.fail(f'Friend {self.friend.username} not found in results')

    def test_recent_note_appears_in_recent_posts(self):
        Note.objects.create(
            author=self.friend, content='just now', visibility=['friends'],
        )
        data = self._get_friend_data()
        self.assertEqual(len(data['recent_posts']), 1)
        self.assertEqual(data['recent_posts'][0]['type'], 'Note')

    def test_old_unread_note_appears(self):
        """An old unread note should appear thanks to the union logic."""
        note = Note.objects.create(
            author=self.friend, content='old unread', visibility=['friends'],
        )
        Note.objects.filter(pk=note.pk).update(
            created_at=timezone.now() - timedelta(hours=48),
        )

        data = self._get_friend_data()
        ids = [p['id'] for p in data['recent_posts']]
        self.assertIn(note.id, ids)

    def test_old_read_note_excluded(self):
        """An old note that's already read should NOT appear."""
        note = Note.objects.create(
            author=self.friend, content='old read', visibility=['friends'],
        )
        Note.objects.filter(pk=note.pk).update(
            created_at=timezone.now() - timedelta(hours=48),
        )
        note.refresh_from_db()
        note.readers.add(self.viewer)

        data = self._get_friend_data()
        ids = [p['id'] for p in data['recent_posts']]
        self.assertNotIn(note.id, ids)

    def test_check_in_component_visibility_matches_profile_endpoint(self):
        """Friend list must not expose components hidden on the profile endpoint."""
        CheckIn.objects.create(
            user=self.friend,
            is_active=True,
            visibility=['friends'],
            social_battery='fully_charged',
            battery_visibility='close_friends',
            mood=['🙂'],
            mood_visibility='close_friends',
            thought='visible to regular friends',
            thought_visibility='friends',
            song_visibility='close_friends',
        )
        Song.objects.create(
            user=self.friend,
            track_id='spotify:track:hidden',
            is_active=True,
        )

        list_data = self._get_friend_data()
        profile_response = self.client.get(f'/api/user/{self.friend.username}/profile/')

        self.assertEqual(profile_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_data['social_battery'], None)
        self.assertEqual(profile_response.data['check_in']['social_battery'], None)
        self.assertEqual(list_data['mood'], None)
        self.assertEqual(profile_response.data['check_in']['mood'], [])
        self.assertEqual(list_data['thought'], 'visible to regular friends')
        self.assertEqual(
            profile_response.data['check_in']['thought'],
            'visible to regular friends',
        )
        self.assertEqual(list_data['track_id'], None)
        self.assertEqual(profile_response.data['check_in']['track_id'], '')

    def test_union_of_recent_and_unread(self):
        """Both a recent-read note and an old-unread note should appear."""
        recent_note = Note.objects.create(
            author=self.friend, content='recent read', visibility=['friends'],
        )
        recent_note.readers.add(self.viewer)

        old_note = Note.objects.create(
            author=self.friend, content='old unread', visibility=['friends'],
        )
        Note.objects.filter(pk=old_note.pk).update(
            created_at=timezone.now() - timedelta(hours=72),
        )

        data = self._get_friend_data()
        ids = [p['id'] for p in data['recent_posts']]
        self.assertIn(recent_note.id, ids)
        self.assertIn(old_note.id, ids)
        self.assertEqual(len(data['recent_posts']), 2)

    def test_visibility_filtering_applied(self):
        """Close-friends-only posts should not appear for regular friends."""
        Note.objects.create(
            author=self.friend, content='secret', visibility=['close_friends'],
        )
        data = self._get_friend_data()
        self.assertEqual(len(data['recent_posts']), 0)
