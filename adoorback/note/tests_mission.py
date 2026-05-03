from datetime import timedelta
from unittest.mock import patch
import zoneinfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from account.models import Connection, DiscoverFeed
from adoorback.models import Mission
from note.models import Note, ShareType

User = get_user_model()


class MissionNoteCreateTests(TestCase):
    """POST /api/notes/ with share_type='mission' should snapshot the prompt
    and assign an attempt number derived from today's mission Note count."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com', password='password'
        )
        self.mission = Mission.objects.create(
            prompt='Share a song that matches your mood right now', type='song'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _post_mission_note(self, content='my response'):
        return self.client.post(
            '/api/notes/',
            data={
                'content': content,
                'visibility': ['friends'],
                'share_type': ShareType.MISSION,
                'mission_id': self.mission.id,
            },
            format='json',
        )

    def test_first_mission_post_assigns_attempt_number_one_and_snapshots_prompt(self):
        response = self._post_mission_note()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        note = Note.objects.get(id=response.data['id'])
        self.assertEqual(note.share_type, ShareType.MISSION)
        self.assertEqual(note.mission_prompt, self.mission.prompt)
        self.assertEqual(note.mission_attempt_number, 1)

    def test_second_mission_post_increments_attempt_number(self):
        self._post_mission_note(content='first')
        response = self._post_mission_note(content='second')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        note = Note.objects.get(id=response.data['id'])
        self.assertEqual(note.mission_attempt_number, 2)

    def test_mission_post_without_mission_id_fails(self):
        response = self.client.post(
            '/api/notes/',
            data={
                'content': 'no mission id',
                'visibility': ['friends'],
                'share_type': ShareType.MISSION,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_mission_post_after_three_attempts_today_fails(self):
        for i in range(3):
            r = self._post_mission_note(content=f'attempt {i + 1}')
            self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)

        fourth = self._post_mission_note(content='attempt 4')
        self.assertEqual(fourth.status_code, status.HTTP_400_BAD_REQUEST)

    def test_mission_post_with_unknown_mission_id_fails(self):
        response = self.client.post(
            '/api/notes/',
            data={
                'content': 'unknown mission',
                'visibility': ['friends'],
                'share_type': ShareType.MISSION,
                'mission_id': 999999,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_regular_note_has_null_mission_fields(self):
        response = self.client.post(
            '/api/notes/',
            data={
                'content': 'just a regular note',
                'visibility': ['friends'],
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        note = Note.objects.get(id=response.data['id'])
        self.assertEqual(note.share_type, ShareType.REGULAR)
        self.assertIsNone(note.mission_prompt)
        self.assertIsNone(note.mission_attempt_number)


class MissionNotePatchTests(TestCase):
    """Mission fields on a Note must be immutable via PATCH."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='bob', email='bob@example.com', password='password'
        )
        self.mission = Mission.objects.create(prompt='Original prompt', type='text')
        self.note = Note.objects.create(
            author=self.user,
            content='original content',
            visibility=['friends'],
            share_type=ShareType.MISSION,
            mission_prompt=self.mission.prompt,
            mission_attempt_number=1,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_patch_content_preserves_mission_fields(self):
        response = self.client.patch(
            f'/api/notes/{self.note.id}/',
            data={'content': 'edited content', 'visibility': ['friends']},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.note.refresh_from_db()
        self.assertEqual(self.note.content, 'edited content')
        self.assertEqual(self.note.share_type, ShareType.MISSION)
        self.assertEqual(self.note.mission_prompt, 'Original prompt')
        self.assertEqual(self.note.mission_attempt_number, 1)

    def test_patch_cannot_change_share_type(self):
        response = self.client.patch(
            f'/api/notes/{self.note.id}/',
            data={
                'content': 'edited',
                'visibility': ['friends'],
                'share_type': ShareType.REGULAR,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.note.refresh_from_db()
        self.assertEqual(self.note.share_type, ShareType.MISSION)

    def test_patch_cannot_change_mission_prompt_or_attempt_number(self):
        response = self.client.patch(
            f'/api/notes/{self.note.id}/',
            data={
                'content': 'edited',
                'visibility': ['friends'],
                'mission_prompt': 'tampered prompt',
                'mission_attempt_number': 99,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.note.refresh_from_db()
        self.assertEqual(self.note.mission_prompt, 'Original prompt')
        self.assertEqual(self.note.mission_attempt_number, 1)


class MissionNoteSerializationTests(TestCase):
    """GET /api/notes/<id>/ should expose share_type, mission_prompt, mission_attempt_number."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='carol', email='carol@example.com', password='password'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_get_mission_note_returns_mission_fields(self):
        note = Note.objects.create(
            author=self.user,
            content='hello',
            visibility=['friends'],
            share_type=ShareType.MISSION,
            mission_prompt='A daily prompt',
            mission_attempt_number=2,
        )

        response = self.client.get(f'/api/notes/{note.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['share_type'], ShareType.MISSION)
        self.assertEqual(response.data['mission_prompt'], 'A daily prompt')
        self.assertEqual(response.data['mission_attempt_number'], 2)

    def test_get_regular_note_returns_null_mission_fields(self):
        note = Note.objects.create(
            author=self.user,
            content='regular',
            visibility=['friends'],
        )

        response = self.client.get(f'/api/notes/{note.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['share_type'], ShareType.REGULAR)
        self.assertIsNone(response.data['mission_prompt'])
        self.assertIsNone(response.data['mission_attempt_number'])


class MissionFeedGroupingTests(TestCase):
    """Mission attempts should collapse into one feed item after visibility filtering."""

    def setUp(self):
        self.author = User.objects.create_user(
            username='mission_author', email='mission_author@example.com', password='password'
        )
        self.friend = User.objects.create_user(
            username='mission_friend', email='mission_friend@example.com', password='password'
        )
        self.stranger = User.objects.create_user(
            username='mission_stranger', email='mission_stranger@example.com', password='password'
        )
        Connection.objects.create(user1=self.author, user2=self.friend)
        self.client = APIClient()

    def _create_mission_attempt(self, content, attempt_number, visibility=None, prompt='Prompt snapshot'):
        return Note.objects.create(
            author=self.author,
            content=content,
            visibility=visibility or ['public'],
            share_type=ShareType.MISSION,
            mission_prompt=prompt,
            mission_attempt_number=attempt_number,
        )

    def test_user_notes_feed_groups_legacy_prompt_attempts_in_attempt_order(self):
        self._create_mission_attempt('first attempt', 1)
        self._create_mission_attempt('second attempt', 2)
        self._create_mission_attempt('third attempt', 3)

        self.client.force_authenticate(user=self.friend)
        response = self.client.get(f'/api/user/{self.author.username}/notes/')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['results']), 1)
        group = response.data['results'][0]
        self.assertEqual(group['type'], 'MissionGroup')
        self.assertIsNone(group['mission_id'])
        self.assertEqual(group['mission_prompt'], 'Prompt snapshot')
        self.assertEqual(group['author_detail']['id'], self.author.id)
        self.assertEqual([attempt['content'] for attempt in group['attempts']], [
            'first attempt',
            'second attempt',
            'third attempt',
        ])
        self.assertEqual([attempt['mission_attempt_number'] for attempt in group['attempts']], [1, 2, 3])

    def test_user_notes_feed_groups_after_visibility_filtering(self):
        self._create_mission_attempt('public attempt', 1, visibility=['public'])
        self._create_mission_attempt('friends attempt', 2, visibility=['friends'])

        self.client.force_authenticate(user=self.friend)
        friend_response = self.client.get(f'/api/user/{self.author.username}/notes/')
        self.assertEqual(friend_response.status_code, status.HTTP_200_OK, friend_response.data)
        self.assertEqual(
            [attempt['content'] for attempt in friend_response.data['results'][0]['attempts']],
            ['public attempt', 'friends attempt'],
        )

        self.client.force_authenticate(user=self.stranger)
        stranger_response = self.client.get(f'/api/user/{self.author.username}/notes/')
        self.assertEqual(stranger_response.status_code, status.HTTP_200_OK, stranger_response.data)
        self.assertEqual(len(stranger_response.data['results']), 1)
        self.assertEqual(stranger_response.data['results'][0]['type'], 'MissionGroup')
        self.assertEqual(
            [attempt['content'] for attempt in stranger_response.data['results'][0]['attempts']],
            ['public attempt'],
        )

    def test_discover_feed_groups_public_mission_attempts(self):
        attempts = [
            self._create_mission_attempt('first discover attempt', 1),
            self._create_mission_attempt('second discover attempt', 2),
            self._create_mission_attempt('third discover attempt', 3),
        ]
        batch_time = timezone.now()
        for index, note in enumerate(reversed(attempts)):
            DiscoverFeed.objects.create(
                user=self.stranger,
                note=note,
                category='discover',
                sort_order=index,
                created_at=batch_time,
            )

        self.client.force_authenticate(user=self.stranger)
        response = self.client.get('/api/user/discover/')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['results']), 1)
        group = response.data['results'][0]
        self.assertEqual(group['type'], 'MissionGroup')
        self.assertEqual(group['category'], 'discover')
        self.assertEqual([attempt['content'] for attempt in group['attempts']], [
            'first discover attempt',
            'second discover attempt',
            'third discover attempt',
        ])


def _at_la_time(year, month, day, hour, minute=0):
    """Helper: build an aware datetime at the given America/Los_Angeles wall-clock time."""
    la_tz = zoneinfo.ZoneInfo('America/Los_Angeles')
    return timezone.datetime(year, month, day, hour, minute, tzinfo=la_tz)


class MissionsTodayEndpointTests(TestCase):
    """GET /api/missions/today/ returns today's mission with attempts_used / attempts_remaining."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='dora', email='dora@example.com', password='password'
        )
        self.other = User.objects.create_user(
            username='ed', email='ed@example.com', password='password'
        )
        self.mission = Mission.objects.create(prompt='Test mission', type='text')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_endpoint_returns_id_prompt_type_and_zero_attempts_for_fresh_user(self):
        response = self.client.get('/api/missions/today/')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn('id', response.data)
        self.assertIn('prompt', response.data)
        self.assertIn('type', response.data)
        self.assertEqual(response.data['attempts_used'], 0)
        self.assertEqual(response.data['attempts_remaining'], 3)
        self.assertEqual(response.data['max_attempts'], 3)

    def test_attempts_used_counts_only_todays_mission_notes_for_request_user(self):
        # Two mission notes for the user today
        Note.objects.create(
            author=self.user, content='a', visibility=['friends'],
            share_type=ShareType.MISSION, mission_prompt='x', mission_attempt_number=1,
        )
        Note.objects.create(
            author=self.user, content='b', visibility=['friends'],
            share_type=ShareType.MISSION, mission_prompt='x', mission_attempt_number=2,
        )
        # A regular note today (should not count)
        Note.objects.create(
            author=self.user, content='c', visibility=['friends'],
        )
        # A mission note today by another user (should not count)
        Note.objects.create(
            author=self.other, content='d', visibility=['friends'],
            share_type=ShareType.MISSION, mission_prompt='x', mission_attempt_number=1,
        )

        response = self.client.get('/api/missions/today/')
        self.assertEqual(response.data['attempts_used'], 2)
        self.assertEqual(response.data['attempts_remaining'], 1)

    def test_attempts_used_excludes_notes_before_todays_7am_la_boundary(self):
        """Notes created before today's 7AM LA boundary should not count."""
        now_la = timezone.now().astimezone(zoneinfo.ZoneInfo('America/Los_Angeles'))
        # An obviously-yesterday timestamp: yesterday at 1AM LA, before any 7AM boundary today.
        yesterday_1am_la = now_la.replace(hour=1, minute=0, second=0, microsecond=0) - timedelta(days=1)

        old_note = Note.objects.create(
            author=self.user, content='old', visibility=['friends'],
            share_type=ShareType.MISSION, mission_prompt='x', mission_attempt_number=1,
        )
        Note.objects.filter(id=old_note.id).update(created_at=yesterday_1am_la)

        response = self.client.get('/api/missions/today/')
        self.assertEqual(response.data['attempts_used'], 0)

    def test_attempts_remaining_floors_at_zero(self):
        for i in range(7):
            Note.objects.create(
                author=self.user, content=f'n{i}', visibility=['friends'],
                share_type=ShareType.MISSION, mission_prompt='x', mission_attempt_number=i + 1,
            )

        response = self.client.get('/api/missions/today/')
        self.assertEqual(response.data['attempts_used'], 7)
        self.assertEqual(response.data['attempts_remaining'], 0)

    def test_endpoint_requires_authentication(self):
        anon = APIClient()
        response = anon.get('/api/missions/today/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


def _create_mission_note_for_test(mission, **kwargs):
    """Attach the mission FK when item #1 has landed; otherwise use prompt fallback."""
    data = {
        'share_type': ShareType.MISSION,
        'mission_prompt': mission.prompt,
        **kwargs,
    }
    note_field_names = {field.name for field in Note._meta.get_fields()}
    if 'mission_id' in note_field_names:
        data['mission_id'] = mission
    elif 'mission' in note_field_names:
        data['mission'] = mission
    return Note.objects.create(**data)


class MissionAttemptsEndpointTests(TestCase):
    """GET /api/missions/<id>/attempts/ returns visible attempts for one mission."""

    def setUp(self):
        self.viewer = User.objects.create_user(
            username='viewer', email='viewer@example.com', password='password'
        )
        self.public_author = User.objects.create_user(
            username='public_author', email='public@example.com', password='password'
        )
        self.friend_author = User.objects.create_user(
            username='friend_author', email='friend@example.com', password='password'
        )
        self.close_author = User.objects.create_user(
            username='close_author', email='close@example.com', password='password'
        )
        self.private_author = User.objects.create_user(
            username='private_author', email='private@example.com', password='password'
        )
        self.unconnected_author = User.objects.create_user(
            username='unconnected_author', email='unconnected@example.com', password='password'
        )
        self.mission = Mission.objects.create(prompt='Share a tiny win from today', type='text')
        self.other_mission = Mission.objects.create(prompt='Share a favorite song', type='song')

        Connection.objects.create(
            user1=self.viewer,
            user2=self.friend_author,
            user1_choice='friend',
            user2_choice='friend',
        )
        Connection.objects.create(
            user1=self.viewer,
            user2=self.close_author,
            user1_choice='friend',
            user2_choice='close_friend',
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.viewer)

    def _set_created_at(self, note, minutes_ago):
        created_at = timezone.now() - timedelta(minutes=minutes_ago)
        Note.objects.filter(id=note.id).update(created_at=created_at)
        note.created_at = created_at
        return note

    def test_endpoint_returns_visible_attempts_with_mission_metadata_newest_first(self):
        old_visible = self._set_created_at(_create_mission_note_for_test(
            self.mission,
            author=self.public_author,
            content='public attempt',
            visibility=['public'],
            mission_attempt_number=1,
        ), 30)
        friend_visible = self._set_created_at(_create_mission_note_for_test(
            self.mission,
            author=self.friend_author,
            content='friends attempt',
            visibility=['friends'],
            mission_attempt_number=2,
        ), 20)
        close_visible = self._set_created_at(_create_mission_note_for_test(
            self.mission,
            author=self.close_author,
            content='close friends attempt',
            visibility=['close_friends'],
            mission_attempt_number=3,
        ), 10)
        _create_mission_note_for_test(
            self.mission,
            author=self.private_author,
            content='private attempt',
            visibility=['only_me'],
            mission_attempt_number=4,
        )
        _create_mission_note_for_test(
            self.mission,
            author=self.unconnected_author,
            content='unconnected friends attempt',
            visibility=['friends'],
            mission_attempt_number=5,
        )
        _create_mission_note_for_test(
            self.other_mission,
            author=self.public_author,
            content='other mission attempt',
            visibility=['public'],
            mission_attempt_number=1,
        )

        response = self.client.get(f'/api/missions/{self.mission.id}/attempts/')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['id'], self.mission.id)
        self.assertEqual(response.data['prompt'], self.mission.prompt)
        self.assertEqual(response.data['type'], self.mission.type)
        self.assertEqual(response.data['count'], 3)
        self.assertIsNone(response.data['previous'])

        result_ids = [item['id'] for item in response.data['results']]
        self.assertEqual(result_ids, [close_visible.id, friend_visible.id, old_visible.id])
        self.assertEqual(response.data['results'][0]['author_detail']['username'], 'close_author')
        self.assertEqual(response.data['results'][0]['mission_attempt_number'], 3)

    def test_endpoint_includes_only_me_attempt_for_author_viewer(self):
        own_note = _create_mission_note_for_test(
            self.mission,
            author=self.viewer,
            content='my private attempt',
            visibility=['only_me'],
            mission_attempt_number=1,
        )

        response = self.client.get(f'/api/missions/{self.mission.id}/attempts/')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], own_note.id)

    def test_endpoint_excludes_attempts_from_different_version_users(self):
        other_ver_author = User.objects.create_user(
            username='other_ver', email='other_ver@example.com', password='password',
            current_ver='version_q',
        )
        other_ver_note = _create_mission_note_for_test(
            self.mission,
            author=other_ver_author,
            content='other version attempt',
            visibility=['public'],
            mission_attempt_number=1,
        )

        response = self.client.get(f'/api/missions/{self.mission.id}/attempts/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = [item['id'] for item in response.data['results']]
        self.assertNotIn(other_ver_note.id, result_ids)

    def test_endpoint_returns_404_for_unknown_mission(self):
        response = self.client.get('/api/missions/999999/attempts/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_endpoint_requires_authentication(self):
        anon = APIClient()
        response = anon.get(f'/api/missions/{self.mission.id}/attempts/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
