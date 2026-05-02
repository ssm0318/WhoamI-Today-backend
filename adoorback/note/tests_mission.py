from datetime import timedelta
from unittest.mock import patch
import zoneinfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

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

    def test_mission_post_after_five_attempts_today_fails(self):
        for i in range(5):
            r = self._post_mission_note(content=f'attempt {i + 1}')
            self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)

        sixth = self._post_mission_note(content='attempt 6')
        self.assertEqual(sixth.status_code, status.HTTP_400_BAD_REQUEST)

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
        self.assertEqual(response.data['attempts_remaining'], 5)
        self.assertEqual(response.data['max_attempts'], 5)

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
        self.assertEqual(response.data['attempts_remaining'], 3)

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
