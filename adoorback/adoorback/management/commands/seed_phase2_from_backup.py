import csv
import os
from datetime import timedelta

import psycopg2
from psycopg2.extras import RealDictCursor

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.db.models.signals import post_save
from django.utils import timezone

from account.models import CustomChip, Interest, User, random_profile_color
from note.models import Note, NoteImage, NoteVideo
from qna.models import Response

from ._seed_phase2_wordlists import generate_unique_fake_username

_VISIBILITY_FIELDS = [
    'name_visibility', 'pronouns_visibility', 'bio_visibility',
    'music_entertainment_visibility', 'hobbies_activities_visibility',
    'on_my_mind_visibility', 'as_a_friend_visibility',
    'online_persona_visibility', 'favorite_platform_visibility',
    'least_favorite_platform_visibility', 'basic_identities_visibility',
    'values_allyship_visibility',
]


class Command(BaseCommand):
    help = (
        'Seed Phase 2 by restoring pre-5/4 posts under new fake user accounts. '
        'Reads Note/Response/profile data from two pg_restore\'d temp DBs, '
        'creates anonymous fake users + posts in the main DB (created_at shifted '
        'by --time-shift-days), then force-regenerates DiscoverFeed for all users. '
        'Run the companion shell script seed_phase2_from_backup.sh first to restore '
        'the dumps into the temp DBs.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--content-db', default='whoamitoday_seed_src',
            help='Temp DB name restored from the content dump (default: whoamitoday_seed_src)',
        )
        parser.add_argument(
            '--profiles-db', default=None,
            help='Temp DB name restored from the profiles dump; defaults to --content-db',
        )
        parser.add_argument(
            '--cutoff-date', default='2026-05-04 00:00:00+00',
            help='Only include posts created strictly before this datetime (default: 2026-05-04 00:00:00+00)',
        )
        parser.add_argument(
            '--time-shift-days', type=int, default=14,
            help='Days to add to each post\'s created_at (default: 14)',
        )
        parser.add_argument(
            '--participants-csv', default=None,
            help='Path to created_users.csv. Auto-located in assets/ if omitted.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print counts without writing anything to the main DB.',
        )
        parser.add_argument(
            '--no-input', action='store_true',
            help='Skip the confirmation prompt.',
        )
        parser.add_argument(
            '--skip-regen', action='store_true',
            help='Skip the DiscoverFeed regeneration step.',
        )
        parser.add_argument(
            '--reset-fakes', action='store_true',
            help='Hard-delete existing fake_*@whoami.test users and their cascaded content first.',
        )
        parser.add_argument(
            '--skip-notes-with-images', action='store_true',
            help='Skip Note rows that have NoteImage attachments (use when note_images/ media dir was wiped).',
        )

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _db_conn(self, dbname):
        db = settings.DATABASES['default']
        return psycopg2.connect(
            host=db.get('HOST', 'localhost'),
            port=int(db.get('PORT', 5432)),
            user=db['USER'],
            password=db.get('PASSWORD', ''),
            dbname=dbname,
        )

    def _locate_csv(self, override):
        if override:
            return override
        # BASE_DIR = .../adoorback/adoorback/ (parent of settings/)
        # assets/ lives at BASE_DIR/assets/
        candidates = [
            os.path.abspath(os.path.join(settings.BASE_DIR, 'assets', 'created_users.csv')),
            os.path.abspath(os.path.join(settings.BASE_DIR, '..', 'assets', 'created_users.csv')),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return candidates[0]

    def _read_participants(self, csv_path):
        emails = set()
        try:
            with open(csv_path, newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    email = (row.get('email') or '').strip().lower()
                    if email:
                        emails.add(email)
        except FileNotFoundError:
            self.stdout.write(self.style.WARNING(f'  participants CSV not found: {csv_path}'))
        return emails

    # ------------------------------------------------------------------ #
    # Temp-DB reads                                                        #
    # ------------------------------------------------------------------ #

    def _fetch_content(self, conn, participant_emails, cutoff_str):
        """Return (authors_by_id, responses, notes, note_images, note_videos)."""
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                'SELECT id, email, username, current_ver, user_group '
                'FROM account_user WHERE deleted IS NULL'
            )
            all_users = {r['id']: dict(r) for r in cur.fetchall()}

            non_participant_ids = [
                uid for uid, u in all_users.items()
                if u['email'].lower() not in participant_emails
            ]
            if not non_participant_ids:
                return {}, [], [], [], []

            cur.execute(
                'SELECT id, author_id, question_id, content, visibility, '
                '       image, video, video_thumbnail, video_duration_seconds, '
                '       created_at '
                'FROM qna_response '
                'WHERE author_id = ANY(%s) AND created_at < %s AND deleted IS NULL',
                [non_participant_ids, cutoff_str],
            )
            responses = [dict(r) for r in cur.fetchall()]

            cur.execute(
                'SELECT id, author_id, content, visibility, share_type, '
                '       mission_id, mission_prompt, mission_attempt_number, '
                '       created_at '
                'FROM note_note '
                'WHERE author_id = ANY(%s) AND created_at < %s AND deleted IS NULL',
                [non_participant_ids, cutoff_str],
            )
            notes = [dict(r) for r in cur.fetchall()]

            note_ids_with_images = {img['note_id'] for img in note_images}

            author_ids_with_content = (
                {r['author_id'] for r in responses} | {n['author_id'] for n in notes}
            )
            authors_by_id = {
                uid: all_users[uid]
                for uid in author_ids_with_content
                if uid in all_users
            }
            if not authors_by_id:
                return {}, [], [], [], []

            note_ids = [n['id'] for n in notes]
            note_images, note_videos = [], []
            if note_ids:
                cur.execute(
                    'SELECT note_id, image FROM note_noteimage WHERE note_id = ANY(%s)',
                    [note_ids],
                )
                note_images = [dict(r) for r in cur.fetchall()]

                # note_notevideo may not exist in older dumps — check first
                cur.execute(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'note_notevideo')"
                )
                if cur.fetchone()['exists']:
                    cur.execute(
                        'SELECT note_id, video, thumbnail, duration_seconds '
                        'FROM note_notevideo WHERE note_id = ANY(%s)',
                        [note_ids],
                    )
                    note_videos = [dict(r) for r in cur.fetchall()]

        return authors_by_id, responses, notes, note_images, note_videos, note_ids_with_images

    def _fetch_profiles(self, conn, author_ids):
        """Return {orig_user_id: profile_dict} with bio/pronouns/persona/visibility/etc."""
        if not author_ids:
            return {}
        fields = ', '.join(['id', 'bio', 'pronouns', 'profile_pic', 'persona',
                            'name', 'timezone', 'language'] + _VISIBILITY_FIELDS)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f'SELECT {fields} FROM account_user '
                'WHERE id = ANY(%s) AND deleted IS NULL',
                [author_ids],
            )
            return {r['id']: dict(r) for r in cur.fetchall()}

    def _fetch_interests(self, conn, author_ids):
        """Return {orig_user_id: [(content, category), ...]}."""
        if not author_ids:
            return {}
        table = Interest.users.through._meta.db_table
        result = {}
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=%s)",
                [table],
            )
            if not cur.fetchone()['exists']:
                return {}
            cur.execute(
                f'SELECT iu.user_id, i.content, i.category '
                f'FROM {table} iu '
                f'JOIN account_interest i ON i.id = iu.interest_id '
                f'WHERE iu.user_id = ANY(%s) AND i.deleted IS NULL',
                [author_ids],
            )
            for row in cur.fetchall():
                result.setdefault(row['user_id'], []).append((row['content'], row['category']))
        return result

    def _fetch_customchips(self, conn, author_ids):
        """Return {orig_user_id: [(text, category), ...]}."""
        if not author_ids:
            return {}
        result = {}
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                'SELECT user_id, text, category FROM account_customchip '
                'WHERE user_id = ANY(%s) AND deleted IS NULL',
                [author_ids],
            )
            for row in cur.fetchall():
                result.setdefault(row['user_id'], []).append((row['text'], row['category']))
        return result

    # ------------------------------------------------------------------ #
    # Main-DB writes                                                       #
    # ------------------------------------------------------------------ #

    def _create_fake_users(self, authors_by_id, profiles_by_id, interests_by_id, chips_by_id):
        """Create one fake User per original author. Returns {orig_id: new_user_id}."""
        import account.models as _acct

        used_usernames = set(User.objects.values_list('username', flat=True))
        id_map = {}

        post_save.disconnect(_acct.user_created, sender=User)
        post_save.disconnect(_acct.provision_wit_admin_rooms, sender=User)
        try:
            with transaction.atomic():
                for orig_id, orig_user in authors_by_id.items():
                    username = generate_unique_fake_username(used_usernames)
                    used_usernames.add(username)
                    email = f'fake_{username}@whoami.test'

                    p = profiles_by_id.get(orig_id, {})
                    persona = p.get('persona') or []

                    user = User(
                        username=username,
                        email=email,
                        bio=p.get('bio'),
                        pronouns=p.get('pronouns'),
                        profile_pic=p.get('profile_pic') or random_profile_color(),
                        profile_image=None,
                        name=p.get('name'),
                        persona=persona,
                        current_ver=orig_user['current_ver'],
                        user_group=orig_user.get('user_group', 'group_w_first'),
                        user_type='indirect',
                        timezone=p.get('timezone') or settings.TIME_ZONE,
                        language=p.get('language') or settings.LANGUAGE_CODE,
                        is_active=True,
                        email_verified=False,
                        **{f: p.get(f, 'public') for f in _VISIBILITY_FIELDS},
                    )
                    user.set_unusable_password()
                    user.save()

                    for content, category in interests_by_id.get(orig_id, []):
                        interest, _ = Interest.objects.get_or_create(
                            content=content, category=category,
                        )
                        user.user_interests.add(interest)

                    for text, category in chips_by_id.get(orig_id, []):
                        CustomChip.objects.get_or_create(
                            user=user, text=text, category=category,
                        )

                    id_map[orig_id] = user.id
                    self.stdout.write(f'  {orig_user["username"]:30s} → {username}')
        finally:
            post_save.connect(_acct.user_created, sender=User)
            post_save.connect(_acct.provision_wit_admin_rooms, sender=User)

        return id_map

    def _create_content(self, responses, notes, note_images, note_videos, id_map, shift_days):
        """Insert Response/Note rows with created_at + shift. Returns (resp_count, note_count)."""
        shift = timedelta(days=shift_days)
        note_id_map = {}
        resp_count = note_count = 0

        with transaction.atomic():
            for r in responses:
                new_author_id = id_map.get(r['author_id'])
                if new_author_id is None:
                    continue
                resp = Response.objects.create(
                    author_id=new_author_id,
                    question_id=r['question_id'],
                    content=r['content'],
                    visibility=r['visibility'] or [],
                    image=r['image'] or '',
                    video=r['video'] or '',
                    video_thumbnail=r['video_thumbnail'] or '',
                    video_duration_seconds=r['video_duration_seconds'],
                )
                if r.get('created_at'):
                    Response.objects.filter(pk=resp.pk).update(
                        created_at=r['created_at'] + shift,
                    )
                resp_count += 1

            for n in notes:
                new_author_id = id_map.get(n['author_id'])
                if new_author_id is None:
                    continue
                note = Note.objects.create(
                    author_id=new_author_id,
                    content=n['content'],
                    visibility=n['visibility'] or [],
                    share_type=n['share_type'],
                    mission_id=n['mission_id'],
                    mission_prompt=n['mission_prompt'],
                    mission_attempt_number=n['mission_attempt_number'],
                )
                if n.get('created_at'):
                    Note.objects.filter(pk=note.pk).update(
                        created_at=n['created_at'] + shift,
                    )
                note_id_map[n['id']] = note.id
                note_count += 1

        with transaction.atomic():
            for img in note_images:
                new_note_id = note_id_map.get(img['note_id'])
                if new_note_id and img.get('image'):
                    NoteImage.objects.create(note_id=new_note_id, image=img['image'])

            for vid in note_videos:
                new_note_id = note_id_map.get(vid['note_id'])
                if new_note_id and vid.get('video'):
                    NoteVideo.objects.create(
                        note_id=new_note_id,
                        video=vid['video'],
                        thumbnail=vid.get('thumbnail') or '',
                        duration_seconds=vid.get('duration_seconds'),
                    )

        return resp_count, note_count

    def _regen_discover_feeds(self):
        """Force-regenerate DiscoverFeed for all active version_w users."""
        from account.models import DiscoverFeed, DiscoverFeedMusic
        from account.views import DiscoverFeedView

        # Clear any stray DiscoverFeed rows for version_q users (should be none)
        DiscoverFeed.objects.filter(user__current_ver='version_q').delete()
        DiscoverFeedMusic.objects.filter(user__current_ver='version_q').delete()

        view = DiscoverFeedView()
        batch_time = timezone.now()

        w_users = list(
            User.objects.filter(is_active=True, deleted__isnull=True, current_ver='version_w')
        )
        for user in w_users:
            view.generate_new_feed(user, batch_time=batch_time)

        total = User.objects.filter(is_active=True, deleted__isnull=True).count()
        return len(w_users), total

    # ------------------------------------------------------------------ #
    # Entry point                                                          #
    # ------------------------------------------------------------------ #

    def handle(self, *args, **options):
        content_dbname = options['content_db']
        profiles_dbname = options['profiles_db'] or content_dbname
        cutoff_str = options['cutoff_date']
        shift_days = options['time_shift_days']
        dry_run = options['dry_run']
        no_input = options['no_input']
        skip_regen = options['skip_regen']
        reset_fakes = options['reset_fakes']
        skip_notes_with_images = options['skip_notes_with_images']

        csv_path = self._locate_csv(options['participants_csv'])
        participant_emails = self._read_participants(csv_path)
        self.stdout.write(
            f'  Participants: {len(participant_emails)} emails from {csv_path}'
        )

        # --- Reset existing fake users ---
        if reset_fakes:
            fake_count = User.objects.filter(email__endswith='@whoami.test').count()
            if fake_count:
                if not no_input:
                    confirm = input(f'Hard-delete {fake_count} existing fake users? Type "YES": ')
                    if confirm != 'YES':
                        self.stdout.write('Aborted.')
                        return
                fake_ids = list(
                    User.objects.filter(email__endswith='@whoami.test')
                    .values_list('id', flat=True)
                )
                with connection.cursor() as cursor:
                    cursor.execute(
                        'DELETE FROM account_user WHERE id = ANY(%s)', [fake_ids]
                    )
                self.stdout.write(self.style.SUCCESS(f'  Deleted {fake_count} existing fake users.'))

        # --- Connect to temp DBs ---
        try:
            content_conn = self._db_conn(content_dbname)
        except Exception as e:
            self.stderr.write(self.style.ERROR(
                f'Cannot connect to content DB "{content_dbname}": {e}'
            ))
            return

        same_db = (profiles_dbname == content_dbname)
        profiles_conn = content_conn
        if not same_db:
            try:
                profiles_conn = self._db_conn(profiles_dbname)
            except Exception as e:
                content_conn.close()
                self.stderr.write(self.style.ERROR(
                    f'Cannot connect to profiles DB "{profiles_dbname}": {e}'
                ))
                return

        try:
            self._run(
                content_conn, profiles_conn, participant_emails,
                cutoff_str, shift_days, dry_run, no_input, skip_regen,
                skip_notes_with_images,
            )
        finally:
            content_conn.close()
            if not same_db:
                profiles_conn.close()

    def _run(self, content_conn, profiles_conn, participant_emails,
             cutoff_str, shift_days, dry_run, no_input, skip_regen, skip_notes_with_images):

        self.stdout.write('\n--- Fetching data from temp DBs ---')
        authors_by_id, responses, notes, note_images, note_videos, note_ids_with_images = \
            self._fetch_content(content_conn, participant_emails, cutoff_str)

        if skip_notes_with_images and note_ids_with_images:
            # Skip only notes that have images AND no meaningful text content
            skipped_ids = {
                n['id'] for n in notes
                if n['id'] in note_ids_with_images and not (n['content'] or '').strip()
            }
            notes = [n for n in notes if n['id'] not in skipped_ids]
            note_images = [img for img in note_images if img['note_id'] not in skipped_ids]
            self.stdout.write(
                f'  Skipping {len(skipped_ids)} image-only notes (no text) '
                f'(--skip-notes-with-images)'
            )

        self.stdout.write(f'  Non-participant authors with posts: {len(authors_by_id)}')
        self.stdout.write(f'  Responses (pre-cutoff):            {len(responses)}')
        self.stdout.write(f'  Notes (pre-cutoff):                {len(notes)}')
        self.stdout.write(f'  NoteImages:                        {len(note_images)}')
        self.stdout.write(f'  NoteVideos:                        {len(note_videos)}')

        author_ids = list(authors_by_id.keys())
        profiles_by_id = self._fetch_profiles(profiles_conn, author_ids)
        interests_by_id = self._fetch_interests(content_conn, author_ids)
        chips_by_id = self._fetch_customchips(content_conn, author_ids)

        if dry_run:
            active_w = User.objects.filter(
                is_active=True, deleted__isnull=True, current_ver='version_w',
            ).count()
            self.stdout.write('\n[DRY RUN] No changes made.')
            self.stdout.write(f'  Would create {len(author_ids)} fake users')
            self.stdout.write(f'  Would create {len(responses)} responses + {len(notes)} notes')
            self.stdout.write(f'  Would regenerate DiscoverFeed for {active_w} version_w users')
            return

        if not no_input:
            active_w = User.objects.filter(
                is_active=True, deleted__isnull=True, current_ver='version_w',
            ).count()
            self.stdout.write(self.style.WARNING(
                f'\nAbout to create {len(author_ids)} fake users, '
                f'{len(responses) + len(notes)} posts (created_at +{shift_days}d), '
                f'and regenerate DiscoverFeed for {active_w} version_w users.'
            ))
            confirm = input('Type "SEED" to proceed: ')
            if confirm != 'SEED':
                self.stdout.write('Aborted.')
                return

        self.stdout.write('\n--- Creating fake users ---')
        id_map = self._create_fake_users(
            authors_by_id, profiles_by_id, interests_by_id, chips_by_id,
        )
        self.stdout.write(self.style.SUCCESS(f'  Created {len(id_map)} fake users.'))

        self.stdout.write('\n--- Creating posts ---')
        resp_count, note_count = self._create_content(
            responses, notes, note_images, note_videos, id_map, shift_days,
        )
        self.stdout.write(self.style.SUCCESS(
            f'  Created {resp_count} responses and {note_count} notes.'
        ))

        if not skip_regen:
            self.stdout.write('\n--- Regenerating DiscoverFeed (version_w users) ---')
            w_count, total = self._regen_discover_feeds()
            self.stdout.write(self.style.SUCCESS(
                f'  Regenerated feed for {w_count} version_w users '
                f'(of {total} active users; version_q is on-demand).'
            ))

        self.stdout.write(self.style.SUCCESS('\nSeed complete.'))
