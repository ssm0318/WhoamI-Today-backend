"""Tests for the restore_experiment_content management command.

The command reads Period-1 content from a separate temp DB (psycopg2) and writes
it onto the live (default) DB via the ORM. These tests mock the two temp-DB
reads (`_fetch_backup_users` and `_fetch_all`) so the restore-write logic runs
against the real test DB as the "live" DB — no second database required.
"""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from account.models import CustomChip, Interest
from check_in.models import CheckIn, CheckInComponentEntry, Song
from comment.models import Comment
from like.models import Like
from note.models import Note
from qna.models import Question, Response
from reaction.models import Reaction

User = get_user_model()

CMD = 'adoorback.management.commands.restore_experiment_content.Command'

# Synthetic backup content_type ids -> (app_label, model).
CTS = {
    100: ('note', 'note'),
    101: ('qna', 'response'),
    102: ('check_in', 'checkin'),
    103: ('check_in', 'checkincomponententry'),
    104: ('comment', 'comment'),
    105: ('check_in', 'checkinpost'),  # not restored
}


def _checkin_row(uid, **over):
    row = dict(
        id=1, user_id=uid, is_active=True, mood=['🙂'], social_battery='low',
        thought='hi', visibility=['public'],
        battery_visibility='friends', mood_visibility='friends',
        song_visibility='public', thought_visibility='friends',
        battery_updated_at=None, mood_updated_at=None, song_updated_at=None,
        thought_updated_at=None, battery_archive_at=None, mood_archive_at=None,
        song_archive_at=None, thought_archive_at=None,
        created_at=timezone.now() - timedelta(days=20),
    )
    row.update(over)
    return row


class RestoreExperimentContentTests(TestCase):
    def setUp(self):
        # Live users (matched by email to the "backup" users id 1 / id 2).
        self.alice = User.objects.create_user(
            username='alice', email='alice@test.com', password='pw',
            current_ver='version_q', user_group='group_w_first',
        )
        self.bob = User.objects.create_user(
            username='bob', email='bob@test.com', password='pw',
            current_ver='version_w', user_group='group_q_first', bio='live bob bio',
        )
        # A question must exist live for responses to be restorable.
        self.q = Question.objects.create(content='Q?', author=self.alice)

        self.backup_users = {1: 'alice@test.com', 2: 'bob@test.com'}
        self.cutoff = '2026-05-18 06:46:14+00'
        self.old = datetime(2026, 5, 10, tzinfo=dt_timezone.utc)

    def _data(self, **over):
        data = dict(
            notes=[dict(id=10, author_id=1, content='old note', visibility=['public'],
                        share_type='regular', mission_id=None, mission_prompt=None,
                        mission_attempt_number=None, is_edited=False, created_at=self.old)],
            note_images=[], note_videos=[],
            responses=[dict(id=20, author_id=1, question_id=self.q.id, content='old answer',
                            visibility=['public'], image=None, video=None,
                            video_thumbnail=None, video_duration_seconds=None,
                            is_edited=False, created_at=self.old)],
            checkins=[_checkin_row(1, created_at=self.old)],
            songs=[dict(id=30, user_id=1, is_active=True, track_id='trk1', created_at=self.old)],
            entries=[dict(id=40, owner_id=1, component='mood', data={'mood': ['🙂']},
                          visibility='friends', superseded_at=None, is_pinned=False,
                          pin_visibility=None, created_at=self.old)],
            interests=[dict(user_id=1, content='Gaming', category='hobbies_activities')],
            chips=[dict(user_id=1, text='custom1', category='hobbies_activities')],
            profiles_by_id={
                1: dict(id=1, persona=['p1'], interests_updated_at=None,
                        personas_updated_at=None, bio='backup alice bio',
                        pronouns=None, name=None, profile_image=None),
                2: dict(id=2, persona=[], interests_updated_at=None,
                        personas_updated_at=None, bio='backup bob bio',
                        pronouns=None, name=None, profile_image=None),
            },
            content_types=dict(CTS),
            comments=[], likes=[], reactions=[],
            readers={'note': [], 'response': [], 'checkin': []},
        )
        data.update(over)
        return data

    def _run(self, data=None, extra=None):
        data = data if data is not None else self._data()
        out = StringIO()
        with mock.patch(f'{CMD}._db_conn', return_value=mock.MagicMock()), \
             mock.patch(f'{CMD}._fetch_backup_users', return_value=self.backup_users), \
             mock.patch(f'{CMD}._fetch_all', return_value=data):
            call_command('restore_experiment_content', '--no-input', '--skip-regen',
                         *(extra or []), stdout=out, stderr=out)
        return out.getvalue()

    def test_restores_authored_content(self):
        self._run()
        self.assertEqual(Note.objects.filter(author=self.alice).count(), 1)
        self.assertEqual(Response.objects.filter(author=self.alice).count(), 1)
        self.assertEqual(CheckIn.objects.filter(user=self.alice).count(), 1)
        self.assertEqual(Song.objects.filter(user=self.alice).count(), 1)
        self.assertEqual(CheckInComponentEntry.objects.filter(owner=self.alice).count(), 1)
        self.assertEqual(self.alice.user_interests.filter(content='Gaming').count(), 1)
        self.assertEqual(CustomChip.objects.filter(user=self.alice, text='custom1').count(), 1)

    def test_original_created_at_preserved(self):
        self._run()
        note = Note.objects.get(author=self.alice)
        self.assertEqual(note.created_at, self.old)

    def test_profile_fill_empty_only(self):
        self._run()
        self.alice.refresh_from_db()
        self.bob.refresh_from_db()
        # Alice had no bio -> filled from backup.
        self.assertEqual(self.alice.bio, 'backup alice bio')
        # Bob already had a bio -> kept (most-recent live value wins).
        self.assertEqual(self.bob.bio, 'live bob bio')
        # persona union.
        self.assertEqual(self.alice.persona, ['p1'])

    def test_idempotent_on_rerun(self):
        self._run()
        self._run()  # second run: alice now has pre-cutoff content -> skipped
        self.assertEqual(Note.objects.filter(author=self.alice).count(), 1)
        self.assertEqual(CheckIn.objects.filter(user=self.alice).count(), 1)

    def test_sets_version_w(self):
        self._run()
        self.alice.refresh_from_db()
        self.bob.refresh_from_db()
        self.assertEqual(self.alice.current_ver, 'version_w')
        self.assertEqual(self.bob.current_ver, 'version_w')

    def test_skip_version_set(self):
        self._run(extra=['--skip-version-set'])
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.current_ver, 'version_q')  # untouched

    def test_response_skipped_when_question_missing(self):
        data = self._data()
        data['responses'][0]['question_id'] = 999999  # no such live question
        self._run(data=data)
        self.assertEqual(Response.objects.filter(author=self.alice).count(), 0)

    def test_single_active_checkin(self):
        # Bob already has a live active check-in; restoring another for bob
        # (backup id 2) must not create a second active row.
        CheckIn.objects.create(user=self.bob, is_active=True, thought='live')
        data = self._data(checkins=[_checkin_row(2, id=2, is_active=True, created_at=self.old)])
        self._run(data=data)
        self.assertEqual(
            CheckIn.objects.filter(user=self.bob, is_active=True).count(), 1
        )

    def test_dry_run_writes_nothing(self):
        out = self._run(extra=['--dry-run'])
        self.assertEqual(Note.objects.filter(author=self.alice).count(), 0)
        self.assertIn('DRY RUN', out)

    def test_restores_engagement_remapped(self):
        # bob (backup id 2) comments + likes alice's note (id 10) and reacts to
        # alice's check-in (id 1); note 10 is read by bob.
        data = self._data(
            comments=[dict(id=50, author_id=2, content='nice', is_private=False,
                           content_type_id=100, object_id=10, created_at=self.old)],
            likes=[dict(id=60, user_id=2, content_type_id=100, object_id=10,
                        created_at=self.old)],
            reactions=[dict(id=70, user_id=2, emoji='🔥', component='mood',
                            content_type_id=102, object_id=1, created_at=self.old)],
            readers={'note': [(10, 2)], 'response': [], 'checkin': []},
        )
        self._run(data=data)
        note = Note.objects.get(author=self.alice)
        ci = CheckIn.objects.get(user=self.alice)
        self.assertEqual(note.note_comments.count(), 1)
        self.assertEqual(note.note_likes.count(), 1)
        self.assertEqual(
            Reaction.objects.filter(
                content_type=ContentType.objects.get_for_model(CheckIn),
                object_id=ci.id,
            ).count(),
            1,
        )
        self.assertTrue(note.readers.filter(id=self.bob.id).exists())

    def test_nested_reply_remapped(self):
        data = self._data(comments=[
            dict(id=50, author_id=2, content='parent', is_private=False,
                 content_type_id=100, object_id=10, created_at=self.old),
            dict(id=51, author_id=1, content='reply', is_private=False,
                 content_type_id=104, object_id=50, created_at=self.old),
        ])
        self._run(data=data)
        self.assertEqual(Comment.objects.count(), 2)
        reply = Comment.objects.get(content='reply')
        parent = Comment.objects.get(content='parent')
        self.assertEqual(reply.content_type, ContentType.objects.get_for_model(Comment))
        self.assertEqual(reply.object_id, parent.id)

    def test_engagement_skipped_for_unrestored_target(self):
        # Like targets a CheckInPost (ct 105), which is never restored -> skipped.
        data = self._data(
            likes=[dict(id=60, user_id=2, content_type_id=105, object_id=999,
                        created_at=self.old)],
        )
        self._run(data=data)
        self.assertEqual(Like.objects.count(), 0)
