import csv
import os
import tempfile
from io import StringIO

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model

from account.models import (
    Connection, CustomChip, DiscoverFeed, FriendRequest,
    Interest, Persona, Subscription,
)
from check_in.models import CheckIn, Song
from comment.models import Comment
from like.models import Like
from note.models import Note
from notification.models import Notification, NotificationActor
from qna.models import Question, Response
from reaction.models import Reaction

User = get_user_model()


class ResetExperimentDataCommandTests(TestCase):
    """Test the reset_experiment_data management command."""

    def setUp(self):
        # Create users
        self.user1 = User.objects.create_user(
            username='alice', email='alice@test.com', password='password',
            current_ver='version_w', user_group='group_w_first',
            bio='Hello!', pronouns='she/her',
            persona=['creative', 'adventurous'],
        )
        self.user2 = User.objects.create_user(
            username='bob', email='bob@test.com', password='password',
            current_ver='version_q', user_group='group_q_first',
            bio='Hey!', pronouns='he/him',
            persona=['analytical'],
        )
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password',
            persona=['admin_persona'],
        )

        # Create a connection (friendship) - should be preserved
        self.connection = Connection.objects.create(
            user1=self.user1, user2=self.user2,
            user1_choice='close_friend', user2_choice='friend',
        )

        # Create an accepted friend request - should be preserved
        self.accepted_fr = FriendRequest.objects.create(
            requester=self.user1, requestee=self.user2, accepted=True,
            requester_choice='close_friend', requestee_choice='friend',
        )

        # Create a pending friend request - should be deleted
        self.user3 = User.objects.create_user(
            username='carol', email='carol@test.com', password='password',
        )
        self.pending_fr = FriendRequest.objects.create(
            requester=self.user1, requestee=self.user3, accepted=None,
            requester_choice='friend',
        )

        # Create content: question (preserved) + response (deleted)
        self.question = Question.objects.create(
            author=self.admin, content='What is your favorite color?',
            is_admin_question=True,
        )
        self.response = Response.objects.create(
            author=self.user1, question=self.question, content='Blue!',
        )

        # Create a note (deleted)
        self.note = Note.objects.create(
            author=self.user1, content='My first note',
        )

        # Create a check-in (deleted)
        self.check_in = CheckIn.objects.create(
            user=self.user1, is_active=True, thought='Feeling good',
        )

        # Create a comment on the note (deleted)
        note_ct = ContentType.objects.get_for_model(Note)
        self.comment = Comment.objects.create(
            author=self.user2, content='Nice note!',
            content_type=note_ct, object_id=self.note.id,
        )

        # Create a like on the note (deleted)
        self.like = Like.objects.create(
            user=self.user2, content_type=note_ct, object_id=self.note.id,
        )

        # Create a reaction on the note (deleted)
        self.reaction = Reaction.objects.create(
            user=self.user2, emoji='😊',
            content_type=note_ct, object_id=self.note.id,
        )

        # Create interests and link to user (M2M cleared, Interest rows preserved)
        self.interest = Interest.objects.create(content='Gaming', category='hobbies_activities')
        self.interest.users.add(self.user1)

        # Create persona and link to user
        self.persona_obj = Persona.objects.create(content='Creative')
        self.persona_obj.users.add(self.user1)

        # Create custom chip (deleted)
        self.chip = CustomChip.objects.create(
            user=self.user1, text='MyChip', category='hobbies_activities',
        )

        # Create subscription (deleted)
        self.subscription = Subscription.objects.create(
            subscriber=self.user2, subscribed_to=self.user1,
            content_type=ContentType.objects.get_for_model(CheckIn),
        )

        # Add favorites and hidden (cleared)
        self.user1.favorites.add(self.user2)
        self.user1.hidden.add(self.user2)

    def _run_command(self, *args, **kwargs):
        out = StringIO()
        kwargs.setdefault('stdout', out)
        kwargs.setdefault('stderr', StringIO())
        call_command('reset_experiment_data', *args, **kwargs)
        return out.getvalue()

    def test_dry_run_does_not_delete(self):
        """Dry run should display counts but not modify any data."""
        output = self._run_command('--dry-run')
        self.assertIn('DRY RUN', output)

        # Everything should still exist
        self.assertEqual(Note.objects.count(), 1)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Comment.objects.count(), 1)
        self.assertEqual(Like.objects.count(), 1)
        self.assertEqual(CheckIn.objects.count(), 1)

    def test_content_is_deleted(self):
        """All user content should be hard-deleted after reset."""
        self._run_command('--skip-backup', '--no-input')

        self.assertEqual(Note.objects.count(), 0)
        self.assertEqual(Response.objects.count(), 0)
        self.assertEqual(Comment.objects.count(), 0)
        self.assertEqual(Like.objects.count(), 0)
        self.assertEqual(Reaction.objects.count(), 0)
        self.assertEqual(CheckIn.objects.count(), 0)
        self.assertEqual(Subscription.objects.count(), 0)
        self.assertEqual(CustomChip.objects.count(), 0)

    def test_notifications_are_deleted(self):
        """All notifications and notification actors should be deleted."""
        # Notifications may have been created by signals during setUp
        noti_count_before = Notification.objects.count()
        actor_count_before = NotificationActor.objects.count()

        self._run_command('--skip-backup', '--no-input')

        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(NotificationActor.objects.count(), 0)

    def test_connections_preserved(self):
        """Friend connections should not be affected."""
        self._run_command('--skip-backup', '--no-input')

        self.assertTrue(Connection.objects.filter(
            user1=self.user1, user2=self.user2
        ).exists())
        conn = Connection.objects.get(user1=self.user1, user2=self.user2)
        self.assertEqual(conn.user1_choice, 'close_friend')
        self.assertEqual(conn.user2_choice, 'friend')

    def test_accepted_friend_request_preserved(self):
        """Accepted friend requests should not be deleted."""
        self._run_command('--skip-backup', '--no-input')

        self.assertTrue(FriendRequest.objects.filter(
            requester=self.user1, requestee=self.user2, accepted=True
        ).exists())

    def test_pending_friend_request_deleted(self):
        """Pending friend requests (accepted=NULL) should be deleted."""
        self._run_command('--skip-backup', '--no-input')

        self.assertFalse(FriendRequest.objects.filter(
            requester=self.user1, requestee=self.user3, accepted=None
        ).exists())

    def test_questions_preserved(self):
        """Admin questions should not be deleted."""
        self._run_command('--skip-backup', '--no-input')

        self.assertTrue(Question.objects.filter(id=self.question.id).exists())

    def test_user_accounts_preserved(self):
        """User accounts with settings should remain intact."""
        self._run_command('--skip-backup', '--no-input')

        self.user1.refresh_from_db()
        self.user2.refresh_from_db()
        self.assertEqual(self.user1.username, 'alice')
        self.assertEqual(self.user2.username, 'bob')
        self.assertEqual(self.user1.email, 'alice@test.com')

    def test_profile_bio_pronouns_preserved(self):
        """Bio and pronouns should NOT be reset."""
        self._run_command('--skip-backup', '--no-input')

        self.user1.refresh_from_db()
        self.assertEqual(self.user1.bio, 'Hello!')
        self.assertEqual(self.user1.pronouns, 'she/her')

    def test_persona_field_reset(self):
        """User persona array field should be cleared to empty."""
        self._run_command('--skip-backup', '--no-input')

        self.user1.refresh_from_db()
        self.user2.refresh_from_db()
        self.assertEqual(self.user1.persona, [])
        self.assertEqual(self.user2.persona, [])

    def test_admin_persona_is_reset(self):
        """Superuser profile fields ARE reset (no superuser filtering)."""
        self._run_command('--skip-backup', '--no-input')

        self.admin.refresh_from_db()
        self.assertEqual(self.admin.persona, [])

    def test_interest_m2m_cleared(self):
        """Interest-user associations should be cleared but Interest rows preserved."""
        self._run_command('--skip-backup', '--no-input')

        # Interest row still exists
        self.assertTrue(Interest.objects.filter(content='Gaming').exists())
        # But user association is gone
        self.assertEqual(self.interest.users.count(), 0)

    def test_persona_m2m_cleared(self):
        """Persona-user associations should be cleared but Persona rows preserved."""
        self._run_command('--skip-backup', '--no-input')

        self.assertTrue(Persona.objects.filter(content='Creative').exists())
        self.assertEqual(self.persona_obj.users.count(), 0)

    def test_favorites_and_hidden_cleared(self):
        """User favorites and hidden M2M should be cleared."""
        self._run_command('--skip-backup', '--no-input')

        self.user1.refresh_from_db()
        self.assertEqual(self.user1.favorites.count(), 0)
        self.assertEqual(self.user1.hidden.count(), 0)

    def test_hard_delete_not_soft_delete(self):
        """Records should be truly gone from the DB, not soft-deleted."""
        self._run_command('--skip-backup', '--no-input')

        # Use raw SQL to check even soft-deleted records
        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM note_note')
            self.assertEqual(cursor.fetchone()[0], 0)

            cursor.execute('SELECT COUNT(*) FROM qna_response')
            self.assertEqual(cursor.fetchone()[0], 0)

            cursor.execute('SELECT COUNT(*) FROM comment_comment')
            self.assertEqual(cursor.fetchone()[0], 0)

    def test_output_shows_summary(self):
        """Command output should include a summary."""
        output = self._run_command('--skip-backup', '--no-input')

        self.assertIn('Experiment data reset complete', output)
        self.assertIn('Total records deleted/cleared', output)

    def _write_exclude_csv(self, emails):
        """Helper: write a temp CSV with the given emails and return its path."""
        fd, path = tempfile.mkstemp(suffix='.csv', prefix='exclude_')
        with os.fdopen(fd, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['email'])
            for e in emails:
                writer.writerow([e])
        self.addCleanup(os.unlink, path)
        return path

    def test_excluded_user_content_preserved(self):
        """Content owned by excluded users must survive the reset."""
        csv_path = self._write_exclude_csv(['alice@test.com'])
        self._run_command('--skip-backup', '--no-input', exclude_emails_csv=csv_path)

        self.assertTrue(Note.objects.filter(id=self.note.id).exists())
        self.assertTrue(Response.objects.filter(id=self.response.id).exists())
        self.assertTrue(CheckIn.objects.filter(id=self.check_in.id).exists())
        self.assertTrue(CustomChip.objects.filter(id=self.chip.id).exists())

    def test_excluded_user_profile_not_reset(self):
        """Excluded users' persona field must not be wiped."""
        csv_path = self._write_exclude_csv(['alice@test.com'])
        self._run_command('--skip-backup', '--no-input', exclude_emails_csv=csv_path)

        self.user1.refresh_from_db()
        self.user2.refresh_from_db()
        self.assertEqual(self.user1.persona, ['creative', 'adventurous'])
        self.assertEqual(self.user2.persona, [])

    def test_excluded_user_m2m_preserved(self):
        """M2M rows touching an excluded user survive."""
        csv_path = self._write_exclude_csv(['alice@test.com'])
        self._run_command('--skip-backup', '--no-input', exclude_emails_csv=csv_path)

        self.user1.refresh_from_db()
        self.assertEqual(self.user1.favorites.count(), 1)
        self.assertEqual(self.user1.hidden.count(), 1)
        self.assertEqual(self.interest.users.count(), 1)
        self.assertEqual(self.persona_obj.users.count(), 1)

    def test_excluded_user_friendrequest_preserved(self):
        """Pending FriendRequest with an excluded user on either side survives."""
        csv_path = self._write_exclude_csv(['alice@test.com'])
        self._run_command('--skip-backup', '--no-input', exclude_emails_csv=csv_path)

        self.assertTrue(FriendRequest.objects.filter(id=self.pending_fr.id).exists())

    def test_non_excluded_user_content_still_deleted(self):
        """Content owned only by non-excluded users is still deleted."""
        # bob (user2) makes a note that nobody on the exclude list authored
        bob_note = Note.objects.create(author=self.user2, content='bob note')
        bob_checkin = CheckIn.objects.create(user=self.user2, is_active=True)

        csv_path = self._write_exclude_csv(['alice@test.com'])
        self._run_command('--skip-backup', '--no-input', exclude_emails_csv=csv_path)

        self.assertFalse(Note.objects.filter(id=bob_note.id).exists())
        self.assertFalse(CheckIn.objects.filter(id=bob_checkin.id).exists())

    def test_exclude_csv_missing_email_column_raises(self):
        """CSV without an 'email' column must abort cleanly."""
        from django.core.management.base import CommandError
        fd, path = tempfile.mkstemp(suffix='.csv')
        with os.fdopen(fd, 'w', newline='') as f:
            f.write('username\nalice\n')
        self.addCleanup(os.unlink, path)

        with self.assertRaises(CommandError):
            self._run_command('--skip-backup', '--no-input', exclude_emails_csv=path)

    def test_note_images_renamed_without_exclusion(self):
        """Without exclusion, note_images/ should be renamed (not deleted)."""
        with tempfile.TemporaryDirectory() as tmp:
            note_images = os.path.join(tmp, 'note_images')
            os.makedirs(note_images)
            sentinel = os.path.join(note_images, 'keep.txt')
            with open(sentinel, 'w') as f:
                f.write('preserve me')
            with override_settings(MEDIA_ROOT=tmp):
                self._run_command('--skip-backup', '--no-input')

            # Original dir exists (recreated empty)
            self.assertTrue(os.path.isdir(note_images))
            self.assertEqual(os.listdir(note_images), [])
            # Renamed backup dir contains the sentinel
            backups = [d for d in os.listdir(tmp) if d.startswith('note_images_backup_')]
            self.assertEqual(len(backups), 1)
            preserved = os.path.join(tmp, backups[0], 'keep.txt')
            self.assertTrue(os.path.isfile(preserved))

    def test_note_images_not_renamed_with_exclusion(self):
        """With exclusion active, note_images/ is left intact (no rename)."""
        csv_path = self._write_exclude_csv(['alice@test.com'])
        with tempfile.TemporaryDirectory() as tmp:
            note_images = os.path.join(tmp, 'note_images')
            os.makedirs(note_images)
            sentinel = os.path.join(note_images, 'keep.txt')
            with open(sentinel, 'w') as f:
                f.write('preserve me in place')
            with override_settings(MEDIA_ROOT=tmp):
                self._run_command('--skip-backup', '--no-input', exclude_emails_csv=csv_path)

            self.assertTrue(os.path.isfile(sentinel))
            backups = [d for d in os.listdir(tmp) if d.startswith('note_images_backup_')]
            self.assertEqual(backups, [])
