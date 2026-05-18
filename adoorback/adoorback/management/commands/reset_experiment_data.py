import os
import shutil
import subprocess
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = (
        'Reset all user-generated content for the experiment phase swap. '
        'Takes a pg_dump backup first, then hard-deletes content via raw SQL '
        '(bypassing Django signals and SafeDelete). '
        'Preserves: Connections, ChatRooms, Messages, User accounts, Questions.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show record counts per table without deleting anything.',
        )
        parser.add_argument(
            '--skip-backup', action='store_true',
            help='Skip the pg_dump backup step (development only).',
        )
        parser.add_argument(
            '--no-input', action='store_true',
            help='Skip the confirmation prompt (for scripted use).',
        )
        parser.add_argument(
            '--backup-dir', type=str, default=None,
            help='Directory for the backup file (default: <project_root>/backups/).',
        )

    def _get_m2m_table_names(self):
        """Resolve auto-generated M2M junction table names at runtime."""
        from account.models import Interest, Persona, User
        from check_in.models import CheckIn
        from note.models import Note
        from qna.models import Response
        return {
            # Content readers (must be cleared before parent tables)
            'response_readers': Response.readers.through._meta.db_table,
            'note_readers': Note.readers.through._meta.db_table,
            'check_in_readers': CheckIn.readers.through._meta.db_table,
            # User-level M2M
            'favorites': User.favorites.through._meta.db_table,
            'hidden': User.hidden.through._meta.db_table,
            'interest_users': Interest.users.through._meta.db_table,
            'persona_users': Persona.users.through._meta.db_table,
        }

    def _get_tables_to_delete(self):
        """Return ordered list of (label, table_name, where_clause) for deletion.

        Order respects FK dependencies: children before parents.
        """
        return [
            # Layer 1: Leaf nodes
            ('NotificationActor', 'notification_notificationactor', None),
            ('UserTag', 'user_tag_usertag', None),
            ('CustomChip', 'account_customchip', None),
            ('PlaylistFeed', 'playlist_playlistfeed', None),
            ('DiscoverFeed', 'account_discoverfeed', None),
            ('DiscoverFeedMusic', 'account_discoverfeedmusic', None),

            # Layer 2: Referenced by Layer 1 (now cleared)
            ('Notification', 'notification_notification', None),
            ('Like', 'like_like', None),
            ('Reaction', 'reaction_reaction', None),
            ('ContentReport', 'content_report_contentreport', None),

            # Layer 3: Comment (self-referential replies)
            ('Comment', 'comment_comment', None),

            # Layer 4: Content tables
            ('NoteImage', 'note_noteimage', None),
            ('Note', 'note_note', None),
            ('ResponseRequest', 'qna_responserequest', None),
            ('Response', 'qna_response', None),

            # Layer 5: Check-in related
            ('Poke', 'check_in_poke', None),
            ('CheckInRead', 'check_in_checkinread', None),
            ('CheckIn', 'check_in_checkin', None),
            ('Song', 'check_in_song', None),

            # Layer 6: Supporting tables
            ('Subscription', 'account_subscription', None),

            # Layer 7: Pending friend requests only
            ('FriendRequest (pending)', 'account_friendrequest', 'accepted IS NULL'),
        ]

    def _run_backup(self, backup_dir):
        """Run pg_dump and return the backup file path."""
        db = settings.DATABASES['default']
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"whoamitoday_pre_reset_{timestamp}.dump"
        filepath = os.path.join(backup_dir, filename)

        env = os.environ.copy()
        env['PGPASSWORD'] = db['PASSWORD']

        cmd = [
            'pg_dump', '-Fc',
            '-h', db.get('HOST', 'localhost'),
            '-p', str(db.get('PORT', '5432')),
            '-U', db.get('USER', 'postgres'),
            '-d', db['NAME'],
            '-f', filepath,
        ]

        self.stdout.write(f'  Running: {" ".join(cmd[:2])} ... -f {filepath}')
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)

        if result.returncode != 0:
            self.stderr.write(self.style.ERROR(f'  pg_dump failed: {result.stderr}'))
            return None

        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(f'  Backup saved: {filepath} ({size_mb:.1f} MB)'))
        return filepath

    def _count_rows(self, cursor, table, where=None):
        """Return row count for a table, optionally with a WHERE clause."""
        sql = f'SELECT COUNT(*) FROM {table}'
        if where:
            sql += f' WHERE {where}'
        try:
            cursor.execute(sql)
            return cursor.fetchone()[0]
        except Exception:
            return -1

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        skip_backup = options['skip_backup']
        no_input = options['no_input']

        # Resolve backup directory
        if options['backup_dir']:
            backup_dir = options['backup_dir']
        else:
            backup_dir = os.path.join(settings.BASE_DIR, '..', 'backups')
        backup_dir = os.path.abspath(backup_dir)

        m2m_tables = self._get_m2m_table_names()
        tables_to_delete = self._get_tables_to_delete()

        # --- Pre-flight: count records ---
        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Experiment Data Reset ===\n'))

        with connection.cursor() as cursor:
            self.stdout.write('M2M junction tables (to be cleared):')
            total = 0
            for name, table in m2m_tables.items():
                count = self._count_rows(cursor, table)
                total += max(count, 0)
                self.stdout.write(f'  {name:30s} {count:>8,}')

            self.stdout.write('\nContent tables (to be deleted):')
            for label, table, where in tables_to_delete:
                count = self._count_rows(cursor, table, where)
                total += max(count, 0)
                suffix = f' (WHERE {where})' if where else ''
                self.stdout.write(f'  {label:30s} {count:>8,}{suffix}')

            self.stdout.write(f'\n  {"TOTAL":30s} {total:>8,} records')

        # --- Profile fields to reset ---
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM account_user "
                "WHERE deleted IS NULL"
            )
            user_count = cursor.fetchone()[0]
        self.stdout.write(f'\nUser profile fields to reset: {user_count} users')
        self.stdout.write('  Fields: persona -> [], interests_updated_at -> NULL, '
                          'personas_updated_at -> NULL, last_interest_card_category -> NULL')

        if dry_run:
            self.stdout.write(self.style.WARNING('\n[DRY RUN] No changes made.'))
            return

        # --- Confirmation ---
        if not no_input:
            self.stdout.write(self.style.WARNING(
                f'\nThis will permanently delete {total:,} records and reset {user_count} user profiles.'
            ))
            confirm = input('Type "RESET" to proceed: ')
            if confirm != 'RESET':
                self.stdout.write(self.style.ERROR('Aborted.'))
                return

        # --- Backup ---
        if not skip_backup:
            self.stdout.write(self.style.MIGRATE_HEADING('\n--- Step 1: Database Backup ---'))
            os.makedirs(backup_dir, exist_ok=True)

            if not shutil.which('pg_dump'):
                self.stderr.write(self.style.ERROR('pg_dump not found on PATH. Aborting.'))
                return

            backup_path = self._run_backup(backup_dir)
            if not backup_path:
                self.stderr.write(self.style.ERROR('Backup failed. Aborting reset.'))
                return
        else:
            self.stdout.write(self.style.WARNING('\n--- Step 1: Backup SKIPPED (--skip-backup) ---'))
            backup_path = None

        # --- Delete data in a single transaction ---
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- Step 2: Deleting Data ---'))

        with connection.cursor() as cursor:
            # All deletions in one transaction
            deleted_counts = {}

            # Clear M2M junction tables first (before parent content tables)
            for name, table in m2m_tables.items():
                cursor.execute(f'DELETE FROM {table}')
                deleted_counts[f'M2M:{name}'] = cursor.rowcount
                self.stdout.write(f'  Cleared {cursor.rowcount:>8,} from M2M {name}')

            # Delete from content tables (FK-dependency order)
            for label, table, where in tables_to_delete:
                sql = f'DELETE FROM {table}'
                if where:
                    sql += f' WHERE {where}'
                cursor.execute(sql)
                deleted_counts[label] = cursor.rowcount
                self.stdout.write(f'  Deleted {cursor.rowcount:>8,} from {label}')

            # Reset user profile fields
            cursor.execute("""
                UPDATE account_user SET
                    persona = '{}',
                    interests_updated_at = NULL,
                    personas_updated_at = NULL,
                    last_interest_card_category = NULL
                WHERE deleted IS NULL
            """)
            profiles_reset = cursor.rowcount
            self.stdout.write(f'  Reset   {profiles_reset:>8,} user profiles')

        # --- Media file cleanup ---
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- Step 3: Media File Cleanup ---'))
        media_root = getattr(settings, 'MEDIA_ROOT', None)
        if media_root:
            note_images_dir = os.path.join(media_root, 'note_images')
            if os.path.isdir(note_images_dir):
                shutil.rmtree(note_images_dir)
                os.makedirs(note_images_dir, exist_ok=True)
                self.stdout.write(f'  Cleared {note_images_dir}')
            else:
                self.stdout.write(f'  No note_images directory found at {note_images_dir}')
        else:
            self.stdout.write('  MEDIA_ROOT not configured, skipping media cleanup.')

        # --- Summary ---
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- Summary ---'))
        total_deleted = sum(v for v in deleted_counts.values())
        self.stdout.write(f'  Total records deleted/cleared: {total_deleted:,}')
        self.stdout.write(f'  User profiles reset: {profiles_reset}')
        if backup_path:
            self.stdout.write(f'  Backup file: {backup_path}')
        self.stdout.write(self.style.SUCCESS('\nExperiment data reset complete.'))
