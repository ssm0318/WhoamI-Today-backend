from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()


class SwapVersionsCommandTests(TestCase):
    """Test the swap_versions management command."""

    def setUp(self):
        self.user_w = User.objects.create_user(
            username='user_w', email='w@test.com', password='password',
            current_ver='version_w', user_group='group_w_first'
        )
        self.user_q = User.objects.create_user(
            username='user_q', email='q@test.com', password='password',
            current_ver='version_q', user_group='group_q_first'
        )
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password'
        )

    def test_swap_all_users(self):
        """Should swap version_w -> version_q and vice versa."""
        out = StringIO()
        call_command('swap_versions', stdout=out)

        self.user_w.refresh_from_db()
        self.user_q.refresh_from_db()
        self.assertEqual(self.user_w.current_ver, 'version_q')
        self.assertEqual(self.user_q.current_ver, 'version_w')

    def test_swap_sets_ver_changed_at(self):
        """Should set ver_changed_at when swapping."""
        self.assertIsNone(self.user_w.ver_changed_at)
        out = StringIO()
        call_command('swap_versions', stdout=out)
        self.user_w.refresh_from_db()
        self.assertIsNotNone(self.user_w.ver_changed_at)

    def test_swap_includes_superusers(self):
        """Superusers are swapped along with everyone else (help text: 'all users')."""
        old_ver = self.admin.current_ver
        expected = 'version_q' if old_ver == 'version_w' else 'version_w'
        out = StringIO()
        call_command('swap_versions', stdout=out)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.current_ver, expected)

    def test_dry_run_does_not_save(self):
        """Dry run should not modify the database."""
        out = StringIO()
        call_command('swap_versions', '--dry-run', stdout=out)
        self.user_w.refresh_from_db()
        self.user_q.refresh_from_db()
        self.assertEqual(self.user_w.current_ver, 'version_w')
        self.assertEqual(self.user_q.current_ver, 'version_q')
        self.assertIn('Would swap', out.getvalue())

    def test_swap_specific_user_ids(self):
        """Should only swap specified users."""
        out = StringIO()
        call_command('swap_versions', '--user-ids', str(self.user_w.id), stdout=out)
        self.user_w.refresh_from_db()
        self.user_q.refresh_from_db()
        self.assertEqual(self.user_w.current_ver, 'version_q')
        self.assertEqual(self.user_q.current_ver, 'version_q')  # unchanged

    def test_double_swap_returns_to_original(self):
        """Swapping twice should return all users to original versions."""
        out = StringIO()
        call_command('swap_versions', stdout=out)
        call_command('swap_versions', stdout=out)
        self.user_w.refresh_from_db()
        self.user_q.refresh_from_db()
        self.assertEqual(self.user_w.current_ver, 'version_w')
        self.assertEqual(self.user_q.current_ver, 'version_q')

    def test_swap_excludes_users_in_csv(self):
        """Users whose email appears in the exclude CSV keep their current_ver."""
        import csv as _csv
        import os
        import tempfile

        fd, path = tempfile.mkstemp(suffix='.csv', prefix='exclude_')
        with os.fdopen(fd, 'w', newline='') as f:
            writer = _csv.writer(f)
            writer.writerow(['email'])
            writer.writerow(['w@test.com'])
        self.addCleanup(os.unlink, path)

        out = StringIO()
        call_command('swap_versions', exclude_emails_csv=path, stdout=out)

        self.user_w.refresh_from_db()
        self.user_q.refresh_from_db()
        self.assertEqual(self.user_w.current_ver, 'version_w')  # excluded
        self.assertEqual(self.user_q.current_ver, 'version_w')  # swapped
