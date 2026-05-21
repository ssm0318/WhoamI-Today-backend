import csv
import os
import shutil
import subprocess
import tarfile
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


def _load_excluded_emails(csv_path):
    """Read a CSV with an 'email' column and return a list of lowercased emails."""
    if not os.path.isfile(csv_path):
        raise CommandError(f'CSV file not found: {csv_path}')

    emails = []
    with open(csv_path, mode='r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or 'email' not in reader.fieldnames:
            raise CommandError(
                f"CSV must have a header row with an 'email' column. "
                f"Found columns: {reader.fieldnames}"
            )
        for row in reader:
            value = (row.get('email') or '').strip().lower()
            if value:
                emails.append(value)
    return emails


def _resolve_excluded_user_ids(cursor, emails):
    """Resolve emails to user IDs. Returns (ids, missing_emails)."""
    if not emails:
        return [], []
    placeholders = ','.join(['%s'] * len(emails))
    cursor.execute(
        f'SELECT id, LOWER(email) FROM account_user WHERE LOWER(email) IN ({placeholders})',
        emails,
    )
    rows = cursor.fetchall()
    found_ids = [row[0] for row in rows]
    found_emails = {row[1] for row in rows}
    missing = [e for e in emails if e not in found_emails]
    return found_ids, missing


def _build_where(user_columns, excluded_ids, base_where=None):
    """Build a WHERE clause that EXCLUDES rows referencing any excluded user.

    A row is preserved (excluded from DELETE) when ANY of its user FKs is in
    excluded_ids. Returns (where_sql_or_None, params_list).
    """
    parts = []
    params = []
    if excluded_ids and user_columns:
        placeholders = ','.join(['%s'] * len(excluded_ids))
        for col in user_columns:
            parts.append(f'{col} NOT IN ({placeholders})')
            params.extend(excluded_ids)
    if base_where:
        parts.append(base_where)
    if not parts:
        return None, []
    return ' AND '.join(parts), params


class Command(BaseCommand):
    help = (
        'Reset all user-generated content for the experiment phase swap. '
        'Takes a pg_dump backup and a MEDIA_ROOT tar.gz snapshot first, then '
        'hard-deletes content via raw SQL (bypassing Django signals and SafeDelete). '
        'Preserves: Connections, ChatRooms, Messages, User accounts, Questions. '
        'With --exclude-emails-csv, the listed users and all their content (and any '
        'M2M rows touching them) are also preserved. Note: generic-FK rows '
        '(notifications/likes/reactions/reports/comments) belonging to preserved '
        'users may end up with dangling target references; Django returns None for '
        'such targets so the UI tolerates it.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show record counts per table without deleting anything.',
        )
        parser.add_argument(
            '--skip-backup', action='store_true',
            help='Skip the pg_dump and media tar.gz backups (development only).',
        )
        parser.add_argument(
            '--no-input', action='store_true',
            help='Skip the confirmation prompt (for scripted use).',
        )
        parser.add_argument(
            '--backup-dir', type=str, default=None,
            help='Directory for backup files (default: <project_root>/backups/).',
        )
        parser.add_argument(
            '--exclude-emails-csv', type=str, default=None,
            help="Path to CSV with an 'email' column. Listed users (and all their "
                 "content + M2M rows that touch them) are preserved.",
        )

    def _get_m2m_specs(self):
        """Resolve auto-generated M2M junction table names + user FK columns."""
        from account.models import Interest, Persona, User
        from check_in.models import CheckIn
        from note.models import Note
        from qna.models import Response
        # (label, table_name, user_columns)
        return [
            ('response_readers', Response.readers.through._meta.db_table, ('user_id',)),
            ('note_readers', Note.readers.through._meta.db_table, ('user_id',)),
            ('check_in_readers', CheckIn.readers.through._meta.db_table, ('user_id',)),
            ('favorites', User.favorites.through._meta.db_table, ('from_user_id', 'to_user_id')),
            ('hidden', User.hidden.through._meta.db_table, ('from_user_id', 'to_user_id')),
            ('interest_users', Interest.users.through._meta.db_table, ('user_id',)),
            ('persona_users', Persona.users.through._meta.db_table, ('user_id',)),
        ]

    def _get_tables_to_delete(self):
        """Return ordered list of (label, table, base_where, user_columns) for deletion.

        Order respects FK dependencies: children before parents. `user_columns`
        is `None` for tables without a direct user FK (handled specially).
        """
        return [
            # Layer 1: Leaf nodes
            ('NotificationActor', 'notification_notificationactor', None, ('user_id',)),
            ('UserTag', 'user_tag_usertag', None, ('tagging_user_id', 'tagged_user_id')),
            ('CustomChip', 'account_customchip', None, ('user_id',)),
            ('PlaylistFeed', 'playlist_playlistfeed', None, ('user_id',)),
            ('DiscoverFeed', 'account_discoverfeed', None, ('user_id',)),
            ('DiscoverFeedMusic', 'account_discoverfeedmusic', None, ('user_id',)),

            # Layer 2: Referenced by Layer 1 (now cleared)
            ('Notification', 'notification_notification', None, ('user_id',)),
            ('Like', 'like_like', None, ('user_id',)),
            ('Reaction', 'reaction_reaction', None, ('user_id',)),
            ('ContentReport', 'content_report_contentreport', None, ('user_id',)),

            # Layer 3: Comment (self-referential replies)
            ('Comment', 'comment_comment', None, ('author_id',)),

            # Layer 4: Content tables
            # NoteImage has no direct user FK; filtered via parent Note.author_id.
            ('NoteImage', 'note_noteimage', None, None),
            ('Note', 'note_note', None, ('author_id',)),
            ('ResponseRequest', 'qna_responserequest', None, ('requester_id', 'requestee_id')),
            ('Response', 'qna_response', None, ('author_id',)),

            # Layer 5: Check-in related
            ('Poke', 'check_in_poke', None, ('sender_id', 'receiver_id')),
            ('CheckInRead', 'check_in_checkinread', None, ('user_id',)),
            ('CheckIn', 'check_in_checkin', None, ('user_id',)),
            ('Song', 'check_in_song', None, ('user_id',)),

            # Layer 6: Supporting tables
            ('Subscription', 'account_subscription', None, ('subscriber_id', 'subscribed_to_id')),

            # Layer 7: FriendEvaluation before FriendRequest (FK dependency)
            ('FriendEvaluation', 'account_friendevaluation', None, ('evaluator_id', 'evaluated_user_id')),
            ('FriendRequest (pending)', 'account_friendrequest', 'accepted IS NULL', ('requester_id', 'requestee_id')),
        ]

    def _run_backup(self, backup_dir, timestamp):
        """Run pg_dump and return the backup file path."""
        db = settings.DATABASES['default']
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

    def _run_media_snapshot(self, backup_dir, timestamp):
        """Tar.gz the entire MEDIA_ROOT to preserve image/video files."""
        media_root = getattr(settings, 'MEDIA_ROOT', None)
        if not media_root or not os.path.isdir(media_root):
            self.stdout.write(self.style.WARNING(
                f'  MEDIA_ROOT not configured or missing ({media_root}); skipping media snapshot.'
            ))
            return None

        filename = f'media_{timestamp}.tar.gz'
        filepath = os.path.join(backup_dir, filename)
        self.stdout.write(f'  Archiving: {media_root} -> {filepath}')
        with tarfile.open(filepath, 'w:gz') as tf:
            tf.add(media_root, arcname='media')

        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(f'  Media snapshot saved: {filepath} ({size_mb:.1f} MB)'))
        return filepath

    def _count_rows(self, cursor, table, where=None, params=None):
        """Return row count for a table, optionally with a WHERE clause."""
        sql = f'SELECT COUNT(*) FROM {table}'
        if where:
            sql += f' WHERE {where}'
        try:
            cursor.execute(sql, params or [])
            return cursor.fetchone()[0]
        except Exception:
            return -1

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        skip_backup = options['skip_backup']
        no_input = options['no_input']
        exclude_csv = options['exclude_emails_csv']

        # Resolve backup directory
        if options['backup_dir']:
            backup_dir = options['backup_dir']
        else:
            backup_dir = os.path.join(settings.BASE_DIR, '..', 'backups')
        backup_dir = os.path.abspath(backup_dir)

        # --- Resolve excluded users (if any) ---
        excluded_emails = []
        excluded_ids = []
        if exclude_csv:
            excluded_emails = _load_excluded_emails(exclude_csv)
            with connection.cursor() as cursor:
                excluded_ids, missing = _resolve_excluded_user_ids(cursor, excluded_emails)
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'\n=== Excluding {len(excluded_ids)} users from reset ==='
            ))
            self.stdout.write(f'  CSV: {exclude_csv}')
            self.stdout.write(f'  Resolved {len(excluded_ids)} of {len(excluded_emails)} emails.')
            if missing:
                self.stdout.write(self.style.WARNING(
                    f'  {len(missing)} email(s) not found in DB: {", ".join(missing[:10])}'
                    + (' ...' if len(missing) > 10 else '')
                ))

        m2m_specs = self._get_m2m_specs()
        tables_to_delete = self._get_tables_to_delete()

        # --- Pre-flight: count records ---
        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Experiment Data Reset ===\n'))

        with connection.cursor() as cursor:
            self.stdout.write('M2M junction tables (to be cleared):')
            total = 0
            for name, table, user_columns in m2m_specs:
                where, params = _build_where(user_columns, excluded_ids)
                count = self._count_rows(cursor, table, where, params)
                total += max(count, 0)
                suffix = ' (excluding preserved users)' if where else ''
                self.stdout.write(f'  {name:30s} {count:>8,}{suffix}')

            self.stdout.write('\nContent tables (to be deleted):')
            for label, table, base_where, user_columns in tables_to_delete:
                if table == 'note_noteimage':
                    # Special-case: count via parent join
                    if excluded_ids:
                        placeholders = ','.join(['%s'] * len(excluded_ids))
                        where = (
                            f'note_id IN (SELECT id FROM note_note '
                            f'WHERE author_id NOT IN ({placeholders}))'
                        )
                        params = list(excluded_ids)
                    else:
                        where, params = None, []
                else:
                    where, params = _build_where(user_columns, excluded_ids, base_where)
                count = self._count_rows(cursor, table, where, params)
                total += max(count, 0)
                base_suffix = f' (WHERE {base_where})' if base_where else ''
                excl_suffix = ' (excluding preserved users)' if excluded_ids else ''
                self.stdout.write(f'  {label:30s} {count:>8,}{base_suffix}{excl_suffix}')

            self.stdout.write(f'\n  {"TOTAL":30s} {total:>8,} records')

        # --- Profile fields to reset ---
        with connection.cursor() as cursor:
            profile_where = 'deleted IS NULL'
            profile_params = []
            if excluded_ids:
                placeholders = ','.join(['%s'] * len(excluded_ids))
                profile_where += f' AND id NOT IN ({placeholders})'
                profile_params.extend(excluded_ids)
            cursor.execute(
                f"SELECT COUNT(*) FROM account_user WHERE {profile_where}",
                profile_params,
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
            if excluded_ids:
                self.stdout.write(self.style.WARNING(
                    f'{len(excluded_ids)} users (from CSV) will be preserved.'
                ))
            confirm = input('Type "RESET" to proceed: ')
            if confirm != 'RESET':
                self.stdout.write(self.style.ERROR('Aborted.'))
                return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # --- Backup ---
        backup_path = None
        media_snapshot_path = None
        if not skip_backup:
            self.stdout.write(self.style.MIGRATE_HEADING('\n--- Step 1: Database Backup ---'))
            os.makedirs(backup_dir, exist_ok=True)

            if not shutil.which('pg_dump'):
                self.stderr.write(self.style.ERROR('pg_dump not found on PATH. Aborting.'))
                return

            backup_path = self._run_backup(backup_dir, timestamp)
            if not backup_path:
                self.stderr.write(self.style.ERROR('Backup failed. Aborting reset.'))
                return

            self.stdout.write(self.style.MIGRATE_HEADING('\n--- Step 1b: Media Snapshot ---'))
            media_snapshot_path = self._run_media_snapshot(backup_dir, timestamp)
            if media_snapshot_path is None and getattr(settings, 'MEDIA_ROOT', None):
                # MEDIA_ROOT is configured but snapshot returned None for some other reason
                self.stderr.write(self.style.ERROR('Media snapshot failed. Aborting reset.'))
                return
        else:
            self.stdout.write(self.style.WARNING('\n--- Step 1: Backup SKIPPED (--skip-backup) ---'))

        # --- Delete data in a single transaction ---
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- Step 2: Deleting Data ---'))

        with connection.cursor() as cursor:
            deleted_counts = {}

            # Clear M2M junction tables first (before parent content tables)
            for name, table, user_columns in m2m_specs:
                where, params = _build_where(user_columns, excluded_ids)
                sql = f'DELETE FROM {table}'
                if where:
                    sql += f' WHERE {where}'
                cursor.execute(sql, params)
                deleted_counts[f'M2M:{name}'] = cursor.rowcount
                self.stdout.write(f'  Cleared {cursor.rowcount:>8,} from M2M {name}')

            # Delete from content tables (FK-dependency order)
            for label, table, base_where, user_columns in tables_to_delete:
                if table == 'note_noteimage':
                    if excluded_ids:
                        placeholders = ','.join(['%s'] * len(excluded_ids))
                        sql = (
                            f'DELETE FROM {table} WHERE note_id IN '
                            f'(SELECT id FROM note_note WHERE author_id NOT IN ({placeholders}))'
                        )
                        params = list(excluded_ids)
                    else:
                        sql = f'DELETE FROM {table}'
                        params = []
                else:
                    where, params = _build_where(user_columns, excluded_ids, base_where)
                    sql = f'DELETE FROM {table}'
                    if where:
                        sql += f' WHERE {where}'
                cursor.execute(sql, params)
                deleted_counts[label] = cursor.rowcount
                self.stdout.write(f'  Deleted {cursor.rowcount:>8,} from {label}')

            # Reset user profile fields (excluding preserved users)
            update_where = 'deleted IS NULL'
            update_params = []
            if excluded_ids:
                placeholders = ','.join(['%s'] * len(excluded_ids))
                update_where += f' AND id NOT IN ({placeholders})'
                update_params.extend(excluded_ids)
            cursor.execute(f"""
                UPDATE account_user SET
                    persona = '{{}}',
                    interests_updated_at = NULL,
                    personas_updated_at = NULL,
                    last_interest_card_category = NULL
                WHERE {update_where}
            """, update_params)
            profiles_reset = cursor.rowcount
            self.stdout.write(f'  Reset   {profiles_reset:>8,} user profiles')

        # --- Media file cleanup ---
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- Step 3: Media File Cleanup ---'))
        media_root = getattr(settings, 'MEDIA_ROOT', None)
        if media_root:
            note_images_dir = os.path.join(media_root, 'note_images')
            if os.path.isdir(note_images_dir):
                if excluded_ids:
                    self.stdout.write(
                        f'  Skipped note_images cleanup; preserved users\' images remain in {note_images_dir}.'
                    )
                    if media_snapshot_path:
                        self.stdout.write(
                            f'  Full media snapshot available at {media_snapshot_path}.'
                        )
                else:
                    renamed = note_images_dir + f'_backup_{timestamp}'
                    os.rename(note_images_dir, renamed)
                    os.makedirs(note_images_dir, exist_ok=True)
                    self.stdout.write(f'  Renamed {note_images_dir} -> {renamed}')
            else:
                self.stdout.write(f'  No note_images directory found at {note_images_dir}')
        else:
            self.stdout.write('  MEDIA_ROOT not configured, skipping media cleanup.')

        # --- Summary ---
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- Summary ---'))
        total_deleted = sum(v for v in deleted_counts.values())
        self.stdout.write(f'  Total records deleted/cleared: {total_deleted:,}')
        self.stdout.write(f'  User profiles reset: {profiles_reset}')
        if excluded_ids:
            self.stdout.write(f'  Users preserved: {len(excluded_ids)}')
        if backup_path:
            self.stdout.write(f'  DB backup: {backup_path}')
        if media_snapshot_path:
            self.stdout.write(f'  Media snapshot: {media_snapshot_path}')
        self.stdout.write(self.style.SUCCESS('\nExperiment data reset complete.'))
