"""Restore Period-1 (pre-swap) user content from a backup DB and move everyone to Ver.W.

Context
-------
During the 5/18 experiment swap, `swap_versions --reset` hard-deleted every
user's authored content and toggled their `current_ver`. The live DB therefore
holds only Period-2 content; Period-1 content survives only in the pre-swap
backup (e.g. backup_20260518_064614.sql). User accounts themselves were
preserved, so this command restores the deleted Period-1 content back onto the
*same* real users (matched by email) for the models that exist in Ver.W, then
sets everyone to `version_w` and regenerates the Discover feed.

Restored (W-compatible content + engagement):
  - Note (+ NoteImage / NoteVideo rows)
  - Response
  - CheckIn / Song / CheckInComponentEntry
  - Interest (M2M) / CustomChip / persona array  (wiped by the reset)
  - profile scalars (bio/pronouns/name/profile_image) — fill-empty only
  - Comment (incl. nested replies), Like, Reaction
  - readers M2M (Note / Response / CheckIn)

Engagement rows reference content via a generic FK (content_type + object_id)
or an M2M through-table, so they are remapped onto the new PKs of the content
restored *in the same run*. Actors are mapped to live users by email; rows whose
target was not restored, or whose actor has no live user, are skipped.

NOT restored (documented limitations):
  - Notification (per request) and UserTag (@mention tags in comments)
  - CheckInPost (Ver.Q-only "story" entity)
  - Image/video *files* — the first swap rmtree'd note_images/, so many
    Period-1 files are gone; only the DB rows are restored (per decision).

The companion shell script `scripts/restore_experiment_content.sh` restores the
backup into a temp DB and then runs this command against it.
"""

from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models.signals import m2m_changed, post_save
from django.utils import timezone

from account.models import CustomChip, Interest, User
from check_in.models import CheckIn, CheckInComponentEntry, Song
from comment.models import Comment
from like.models import Like
from note.models import Note, NoteImage, NoteVideo
from qna.models import Question, Response
from reaction.models import Reaction


@contextmanager
def _muted_signals():
    """Disable ALL post_save / m2m_changed receivers in THIS process for a restore.

    A restore must not fire notifications, Firebase push threads, reader
    auto-adds, etc. Disconnecting receivers individually is fragile: a receiver
    wrapped by ``@transaction.atomic`` stacked above ``@receiver`` is registered
    under a *different* object than the module attribute, so
    ``disconnect(module.func)`` silently misses it (this caused a push-
    notification storm on the first run). Instead we swap out the receiver lists
    wholesale and restore them afterward. Safe because the management command
    runs in its own process — live gunicorn workers keep their signals.
    """
    saved = []
    for sig in (post_save, m2m_changed):
        saved.append((sig, sig.receivers))
        sig.receivers = []
        sig.sender_receivers_cache.clear()
    try:
        yield
    finally:
        for sig, receivers in saved:
            sig.receivers = receivers
            sig.sender_receivers_cache.clear()


# Profile scalar fields restored fill-empty (only when the live value is blank).
_PROFILE_SCALAR_FIELDS = ['bio', 'pronouns', 'name', 'profile_image']

# Swap happened 2026-05-18 06:46:14 UTC. Live content all postdates this, so any
# live row with created_at < cutoff is a prior restore — used for idempotency.
_DEFAULT_RESTORED_BEFORE = '2026-05-18 06:46:14+00'


class Command(BaseCommand):
    help = (
        'Restore Period-1 authored content + engagement (Note/Response/CheckIn/'
        'Interest/CustomChip/persona/profile + Comment/Like/Reaction/readers) '
        'from a backup temp DB onto the same real users, then set everyone to '
        'version_w and regenerate Discover feeds. Run '
        'scripts/restore_experiment_content.sh first to load the backup into '
        'the temp DB.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--content-db', default='whoamitoday_restore_src',
            help='Temp DB name restored from the backup (default: whoamitoday_restore_src)',
        )
        parser.add_argument(
            '--restored-before', default=_DEFAULT_RESTORED_BEFORE,
            help='Idempotency cutoff: skip a user/type if they already have live '
                 f'content created before this datetime (default: {_DEFAULT_RESTORED_BEFORE})',
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
            '--skip-version-set', action='store_true',
            help='Do not set users to version_w (restore content only).',
        )
        parser.add_argument(
            '--skip-regen', action='store_true',
            help='Skip the DiscoverFeed regeneration step.',
        )

    # ------------------------------------------------------------------ #
    # Temp-DB helpers                                                      #
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

    def _table_exists(self, cur, table):
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_name = %s)",
            [table],
        )
        return cur.fetchone()['exists']

    def _existing_columns(self, cur, table):
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s",
            [table],
        )
        return {row['column_name'] for row in cur.fetchall()}

    def _select_available(self, cur, table, wanted, where, params):
        """SELECT only the columns of `wanted` that actually exist in the dump.

        Guards against schema drift between the 5/18 backup and the current
        models (e.g. columns added by later migrations). Returns list of dicts;
        missing columns are filled with None.
        """
        if not self._table_exists(cur, table):
            return []
        present = self._existing_columns(cur, table)
        cols = [c for c in wanted if c in present]
        if not cols:
            return []
        cur.execute(
            f'SELECT {", ".join(cols)} FROM {table} WHERE {where}',
            params,
        )
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            for c in wanted:
                r.setdefault(c, None)
        return rows

    # ------------------------------------------------------------------ #
    # Live-DB write helpers                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _set_created_at(model, pk, created_at):
        """Override auto_now_add created_at via a queryset update (bypasses save)."""
        if created_at:
            model.objects.filter(pk=pk).update(created_at=created_at)

    def _user_already_restored(self, live_user, cutoff):
        """True if this user already has pre-cutoff live content (prior restore)."""
        return (
            Note.objects.filter(author=live_user, created_at__lt=cutoff).exists()
            or Response.objects.filter(author=live_user, created_at__lt=cutoff).exists()
            or CheckIn.objects.filter(user=live_user, created_at__lt=cutoff).exists()
        )

    # ------------------------------------------------------------------ #
    # Entry point                                                          #
    # ------------------------------------------------------------------ #

    def handle(self, *args, **options):
        content_db = options['content_db']
        cutoff = options['restored_before']
        dry_run = options['dry_run']
        no_input = options['no_input']
        skip_version_set = options['skip_version_set']
        skip_regen = options['skip_regen']

        try:
            conn = self._db_conn(content_db)
        except Exception as e:
            self.stderr.write(self.style.ERROR(
                f'Cannot connect to backup DB "{content_db}": {e}'
            ))
            return

        try:
            self._run(conn, cutoff, dry_run, no_input, skip_version_set, skip_regen)
        finally:
            conn.close()

    def _fetch_backup_users(self, conn):
        """Return {backup_user_id: lowercased_email} for real (non-fake) users."""
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                'SELECT id, email FROM account_user '
                "WHERE deleted IS NULL AND email NOT LIKE '%%@whoami.test'"
            )
            return {r['id']: (r['email'] or '').strip().lower() for r in cur.fetchall()}

    def _run(self, conn, cutoff, dry_run, no_input, skip_version_set, skip_regen):
        # --- Step 0: map backup users -> live users by email --------------- #
        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Mapping backup users to live users ==='))
        backup_users = self._fetch_backup_users(conn)

        live_by_email = {
            (u.email or '').strip().lower(): u
            for u in User.objects.filter(deleted__isnull=True)
        }
        # {backup_user_id: live_user}
        user_map = {}
        unmatched = []
        for bid, email in backup_users.items():
            live = live_by_email.get(email)
            if live is not None:
                user_map[bid] = live
            elif email:
                unmatched.append(email)

        self.stdout.write(f'  Backup users (real):  {len(backup_users)}')
        self.stdout.write(f'  Matched to live:      {len(user_map)}')
        if unmatched:
            self.stdout.write(self.style.WARNING(
                f'  Unmatched (skipped):  {len(unmatched)} '
                f'e.g. {", ".join(unmatched[:5])}'
            ))

        if not user_map:
            self.stdout.write(self.style.WARNING('No users to restore. Aborting.'))
            return

        # --- Fetch all content + engagement for matched backup users ------ #
        backup_ids = list(user_map.keys())
        data = self._fetch_all(conn, backup_ids)

        # --- Idempotency: drop users that already have restored content --- #
        skipped_users = set()
        for bid, live in user_map.items():
            if self._user_already_restored(live, cutoff):
                skipped_users.add(bid)
        if skipped_users:
            self.stdout.write(self.style.WARNING(
                f'\n  {len(skipped_users)} users already have pre-cutoff content '
                f'(< {cutoff}) — skipping their content (idempotency).'
            ))

        def _live_for(bid):
            if bid in skipped_users:
                return None
            return user_map.get(bid)

        # --- Count summary ------------------------------------------------- #
        active_ids = {b for b in backup_ids if b not in skipped_users}
        n_notes = sum(1 for n in data['notes'] if n['author_id'] in active_ids)
        n_resp = sum(1 for r in data['responses'] if r['author_id'] in active_ids)
        n_ci = sum(1 for c in data['checkins'] if c['user_id'] in active_ids)
        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Restore plan ==='))
        self.stdout.write(f'  Users to restore:    {len(active_ids)}')
        self.stdout.write(f'  Notes:               {n_notes}')
        self.stdout.write(f'  Responses:           {n_resp}')
        self.stdout.write(f'  CheckIns:            {n_ci}')
        self.stdout.write(f'  Songs:               {len(data["songs"])}')
        self.stdout.write(f'  ComponentEntries:    {len(data["entries"])}')
        self.stdout.write(f'  Interests rows:      {len(data["interests"])}')
        self.stdout.write(f'  CustomChips:         {len(data["chips"])}')
        self.stdout.write(f'  Comments (cand.):    {len(data["comments"])}')
        self.stdout.write(f'  Likes (cand.):       {len(data["likes"])}')
        self.stdout.write(f'  Reactions (cand.):   {len(data["reactions"])}')
        self.stdout.write(f'  Reader rows (cand.): '
                          f'{sum(len(v) for v in data["readers"].values())}')

        if dry_run:
            self.stdout.write(self.style.WARNING('\n[DRY RUN] No changes made.'))
            return

        if not no_input:
            confirm = input('\nType "RESTORE" to proceed: ')
            if confirm != 'RESTORE':
                self.stdout.write(self.style.ERROR('Aborted.'))
                return

        # All writes run with signals muted: a restore must not fire any
        # notifications / Firebase push threads / reader auto-adds. See
        # _muted_signals() for why this is global rather than per-receiver.
        with _muted_signals():
            # --- Steps 1-4: content (capture old->new id maps) ------------- #
            note_id_map = self._restore_notes(data, _live_for)
            response_id_map = self._restore_responses(data, _live_for)
            checkin_id_map = self._restore_checkins(data, _live_for)
            self._restore_songs(data, _live_for)
            entry_id_map = self._restore_entries(data, _live_for)

            # --- Step 5-6: Interests / CustomChips / persona / profile ----- #
            self._restore_profile_and_chips(data, _live_for)

            # --- Engagement: Comment -> Like/Reaction -> readers ----------- #
            comment_id_map = self._restore_comments(
                data, user_map, note_id_map, response_id_map, checkin_id_map, entry_id_map,
            )
            target_maps = {
                ('note', 'note'): (note_id_map, Note),
                ('qna', 'response'): (response_id_map, Response),
                ('check_in', 'checkin'): (checkin_id_map, CheckIn),
                ('check_in', 'checkincomponententry'): (entry_id_map, CheckInComponentEntry),
                ('comment', 'comment'): (comment_id_map, Comment),
            }
            self._restore_likes(data, user_map, target_maps)
            self._restore_reactions(data, user_map, target_maps)
            self._restore_readers(data, user_map, note_id_map, response_id_map, checkin_id_map)

            # --- Step 7: set everyone to version_w ------------------------- #
            if not skip_version_set:
                now = timezone.now()
                updated = (
                    User.objects.filter(deleted__isnull=True)
                    .exclude(email__endswith='@whoami.test')
                    .update(current_ver='version_w', ver_changed_at=now)
                )
                self.stdout.write(self.style.SUCCESS(
                    f'\n  Set {updated} users to version_w.'
                ))

            # --- Step 8: regenerate Discover feed -------------------------- #
            if not skip_regen:
                self.stdout.write('\n--- Regenerating DiscoverFeed (version_w users) ---')
                w_count = self._regen_discover_feeds()
                self.stdout.write(self.style.SUCCESS(
                    f'  Regenerated feed for {w_count} version_w users.'
                ))

        self.stdout.write(self.style.SUCCESS('\nRestore complete.'))

    # ------------------------------------------------------------------ #
    # Fetch                                                                #
    # ------------------------------------------------------------------ #

    def _fetch_all(self, conn, backup_ids):
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            notes = self._select_available(
                cur, 'note_note',
                ['id', 'author_id', 'content', 'visibility', 'share_type',
                 'mission_id', 'mission_prompt', 'mission_attempt_number',
                 'is_edited', 'created_at'],
                'author_id = ANY(%s) AND deleted IS NULL', [backup_ids],
            )
            note_ids = [n['id'] for n in notes]
            note_images = self._select_available(
                cur, 'note_noteimage', ['note_id', 'image'],
                'note_id = ANY(%s)', [note_ids],
            ) if note_ids else []
            note_videos = self._select_available(
                cur, 'note_notevideo',
                ['note_id', 'video', 'thumbnail', 'duration_seconds'],
                'note_id = ANY(%s)', [note_ids],
            ) if note_ids else []

            responses = self._select_available(
                cur, 'qna_response',
                ['id', 'author_id', 'question_id', 'content', 'visibility',
                 'image', 'video', 'video_thumbnail', 'video_duration_seconds',
                 'is_edited', 'created_at'],
                'author_id = ANY(%s) AND deleted IS NULL', [backup_ids],
            )

            checkins = self._select_available(
                cur, 'check_in_checkin',
                ['id', 'user_id', 'is_active', 'mood', 'social_battery', 'thought',
                 'visibility',
                 'battery_visibility', 'mood_visibility', 'song_visibility',
                 'thought_visibility',
                 'battery_updated_at', 'mood_updated_at', 'song_updated_at',
                 'thought_updated_at',
                 'battery_archive_at', 'mood_archive_at', 'song_archive_at',
                 'thought_archive_at', 'created_at'],
                'user_id = ANY(%s) AND deleted IS NULL', [backup_ids],
            )
            songs = self._select_available(
                cur, 'check_in_song',
                ['id', 'user_id', 'is_active', 'track_id', 'created_at'],
                'user_id = ANY(%s) AND deleted IS NULL', [backup_ids],
            )
            entries = self._select_available(
                cur, 'check_in_checkincomponententry',
                ['id', 'owner_id', 'component', 'data', 'visibility',
                 'superseded_at', 'is_pinned', 'pin_visibility', 'created_at'],
                'owner_id = ANY(%s) AND deleted IS NULL', [backup_ids],
            )

            # Interests M2M -> (user_id, content, category)
            interests = []
            itable = Interest.users.through._meta.db_table
            if self._table_exists(cur, itable):
                cur.execute(
                    f'SELECT iu.user_id, i.content, i.category '
                    f'FROM {itable} iu '
                    f'JOIN account_interest i ON i.id = iu.interest_id '
                    f'WHERE iu.user_id = ANY(%s) AND i.deleted IS NULL',
                    [backup_ids],
                )
                interests = [dict(r) for r in cur.fetchall()]

            chips = self._select_available(
                cur, 'account_customchip',
                ['user_id', 'text', 'category'],
                'user_id = ANY(%s) AND deleted IS NULL', [backup_ids],
            )

            profiles = self._select_available(
                cur, 'account_user',
                ['id', 'persona', 'interests_updated_at', 'personas_updated_at']
                + _PROFILE_SCALAR_FIELDS,
                'id = ANY(%s) AND deleted IS NULL', [backup_ids],
            )
            profiles_by_id = {p['id']: p for p in profiles}

            # --- Engagement: content_type map + comments/likes/reactions --- #
            content_types = {}
            if self._table_exists(cur, 'django_content_type'):
                cur.execute('SELECT id, app_label, model FROM django_content_type')
                content_types = {r['id']: (r['app_label'], r['model']) for r in cur.fetchall()}

            comments = self._select_available(
                cur, 'comment_comment',
                ['id', 'author_id', 'content', 'is_private',
                 'content_type_id', 'object_id', 'created_at'],
                'author_id = ANY(%s) AND deleted IS NULL', [backup_ids],
            )
            likes = self._select_available(
                cur, 'like_like',
                ['id', 'user_id', 'content_type_id', 'object_id', 'created_at'],
                'user_id = ANY(%s) AND deleted IS NULL', [backup_ids],
            )
            reactions = self._select_available(
                cur, 'reaction_reaction',
                ['id', 'user_id', 'emoji', 'component',
                 'content_type_id', 'object_id', 'created_at'],
                'user_id = ANY(%s) AND deleted IS NULL', [backup_ids],
            )

            # --- readers M2M through-tables (Note/Response/CheckIn) -------- #
            readers = {}
            reader_specs = [
                ('note', Note.readers.through._meta.db_table, 'note_id', note_ids),
                ('response', Response.readers.through._meta.db_table, 'response_id',
                 [r['id'] for r in responses]),
                ('checkin', CheckIn.readers.through._meta.db_table, 'checkin_id',
                 [c['id'] for c in checkins]),
            ]
            for key, table, col, ids in reader_specs:
                rows = []
                if ids and self._table_exists(cur, table):
                    cur.execute(
                        f'SELECT {col} AS src_id, user_id FROM {table} WHERE {col} = ANY(%s)',
                        [ids],
                    )
                    rows = [(r['src_id'], r['user_id']) for r in cur.fetchall()]
                readers[key] = rows

        return {
            'notes': notes, 'note_images': note_images, 'note_videos': note_videos,
            'responses': responses, 'checkins': checkins, 'songs': songs,
            'entries': entries, 'interests': interests, 'chips': chips,
            'profiles_by_id': profiles_by_id,
            'content_types': content_types, 'comments': comments,
            'likes': likes, 'reactions': reactions, 'readers': readers,
        }

    # ------------------------------------------------------------------ #
    # Restore steps — content                                              #
    # ------------------------------------------------------------------ #

    def _restore_notes(self, data, live_for):
        """Recreate Notes with new PKs, original created_at; remap images/videos.

        Returns {backup_note_id: new_note_id}.
        """
        note_id_map = {}
        created = 0
        with transaction.atomic():
            for n in data['notes']:
                live = live_for(n['author_id'])
                if live is None:
                    continue
                note = Note.objects.create(
                    author=live,
                    content=n['content'],
                    visibility=n['visibility'] or [],
                    share_type=n['share_type'] or 'regular',
                    mission_id=n['mission_id'],
                    mission_prompt=n['mission_prompt'],
                    mission_attempt_number=n['mission_attempt_number'],
                    is_edited=bool(n['is_edited']),
                )
                self._set_created_at(Note, note.pk, n['created_at'])
                note_id_map[n['id']] = note.pk
                created += 1

            for img in data['note_images']:
                new_id = note_id_map.get(img['note_id'])
                if new_id and img.get('image'):
                    NoteImage.objects.create(note_id=new_id, image=img['image'])
            for vid in data['note_videos']:
                new_id = note_id_map.get(vid['note_id'])
                if new_id and vid.get('video'):
                    NoteVideo.objects.create(
                        note_id=new_id, video=vid['video'],
                        thumbnail=vid.get('thumbnail') or '',
                        duration_seconds=vid.get('duration_seconds'),
                    )
        self.stdout.write(self.style.SUCCESS(f'  Restored {created} notes.'))
        return note_id_map

    def _restore_responses(self, data, live_for):
        """Recreate Responses; skip rows whose question no longer exists live.

        Returns {backup_response_id: new_response_id}.
        """
        response_id_map = {}
        live_question_ids = set(Question.objects.values_list('id', flat=True))
        created = skipped = 0
        with transaction.atomic():
            for r in data['responses']:
                live = live_for(r['author_id'])
                if live is None:
                    continue
                if r['question_id'] not in live_question_ids:
                    skipped += 1
                    continue
                resp = Response.objects.create(
                    author=live,
                    question_id=r['question_id'],
                    content=r['content'],
                    visibility=r['visibility'] or [],
                    image=r['image'] or '',
                    video=r['video'] or '',
                    video_thumbnail=r['video_thumbnail'] or '',
                    video_duration_seconds=r['video_duration_seconds'],
                    is_edited=bool(r['is_edited']),
                )
                self._set_created_at(Response, resp.pk, r['created_at'])
                response_id_map[r['id']] = resp.pk
                created += 1
        msg = f'  Restored {created} responses.'
        if skipped:
            msg += f' (skipped {skipped} with missing question)'
        self.stdout.write(self.style.SUCCESS(msg))
        return response_id_map

    def _restore_checkins(self, data, live_for):
        """bulk_create CheckIns (bypasses heavy save()/signals); one active per user.

        Returns {backup_checkin_id: new_checkin_id}.
        """
        live_active_uids = set(
            CheckIn.objects.filter(is_active=True, deleted__isnull=True)
            .values_list('user_id', flat=True)
        )
        objs, srcs, seen_active = [], [], set()
        for c in data['checkins']:
            live = live_for(c['user_id'])
            if live is None:
                continue
            active = bool(c['is_active'])
            if active and (live.id in live_active_uids or live.id in seen_active):
                active = False
            if active:
                seen_active.add(live.id)
            objs.append(CheckIn(
                user=live, is_active=active,
                mood=c['mood'] or [], social_battery=c['social_battery'],
                thought=c['thought'], visibility=c['visibility'] or ['public'],
                battery_visibility=c['battery_visibility'] or 'friends',
                mood_visibility=c['mood_visibility'] or 'friends',
                song_visibility=c['song_visibility'] or 'public',
                thought_visibility=c['thought_visibility'] or 'friends',
                battery_updated_at=c['battery_updated_at'],
                mood_updated_at=c['mood_updated_at'],
                song_updated_at=c['song_updated_at'],
                thought_updated_at=c['thought_updated_at'],
                battery_archive_at=c['battery_archive_at'],
                mood_archive_at=c['mood_archive_at'],
                song_archive_at=c['song_archive_at'],
                thought_archive_at=c['thought_archive_at'],
            ))
            srcs.append(c)
        created = CheckIn.objects.bulk_create(objs)
        checkin_id_map = {}
        for obj, src in zip(created, srcs):
            self._set_created_at(CheckIn, obj.pk, src['created_at'])
            checkin_id_map[src['id']] = obj.pk
        self.stdout.write(self.style.SUCCESS(f'  Restored {len(created)} check-ins.'))
        return checkin_id_map

    def _restore_songs(self, data, live_for):
        live_active_uids = set(
            Song.objects.filter(is_active=True, deleted__isnull=True)
            .values_list('user_id', flat=True)
        )
        objs, srcs, seen_active = [], [], set()
        for s in data['songs']:
            live = live_for(s['user_id'])
            if live is None:
                continue
            active = bool(s['is_active'])
            if active and (live.id in live_active_uids or live.id in seen_active):
                active = False
            if active:
                seen_active.add(live.id)
            objs.append(Song(user=live, is_active=active, track_id=s['track_id']))
            srcs.append(s)
        created = Song.objects.bulk_create(objs)
        for obj, src in zip(created, srcs):
            self._set_created_at(Song, obj.pk, src['created_at'])
        self.stdout.write(self.style.SUCCESS(f'  Restored {len(created)} songs.'))

    def _restore_entries(self, data, live_for):
        """Returns {backup_entry_id: new_entry_id}."""
        objs, srcs = [], []
        for e in data['entries']:
            live = live_for(e['owner_id'])
            if live is None:
                continue
            objs.append(CheckInComponentEntry(
                owner=live, component=e['component'],
                data=e['data'] or {}, visibility=e['visibility'] or 'friends',
                superseded_at=e['superseded_at'],
                is_pinned=bool(e['is_pinned']),
                pin_visibility=e['pin_visibility'],
            ))
            srcs.append(e)
        created = CheckInComponentEntry.objects.bulk_create(objs)
        entry_id_map = {}
        for obj, src in zip(created, srcs):
            self._set_created_at(CheckInComponentEntry, obj.pk, src['created_at'])
            entry_id_map[src['id']] = obj.pk
        self.stdout.write(self.style.SUCCESS(
            f'  Restored {len(created)} check-in component entries.'
        ))
        return entry_id_map

    def _restore_profile_and_chips(self, data, live_for):
        """Restore interests/chips (merge), persona (union), profile scalars (fill-empty)."""
        interests_by_uid = {}
        for row in data['interests']:
            interests_by_uid.setdefault(row['user_id'], []).append(
                (row['content'], row['category'])
            )
        chips_by_uid = {}
        for row in data['chips']:
            chips_by_uid.setdefault(row['user_id'], []).append(
                (row['text'], row['category'])
            )

        n_interest = n_chip = n_profile = 0
        with transaction.atomic():
            for bid in {*interests_by_uid, *chips_by_uid, *data['profiles_by_id']}:
                live = live_for(bid)
                if live is None:
                    continue

                for content, category in interests_by_uid.get(bid, []):
                    interest, _ = Interest.objects.get_or_create(
                        content=content, category=category or 'hobbies_activities',
                    )
                    live.user_interests.add(interest)
                    n_interest += 1

                for text, category in chips_by_uid.get(bid, []):
                    _, was_created = CustomChip.objects.get_or_create(
                        user=live, text=text, category=category,
                    )
                    n_chip += 1 if was_created else 0

                p = data['profiles_by_id'].get(bid)
                if not p:
                    continue
                dirty = []
                backup_persona = p.get('persona') or []
                if backup_persona:
                    merged = list(live.persona or [])
                    for item in backup_persona:
                        if item not in merged:
                            merged.append(item)
                    if merged != list(live.persona or []):
                        live.persona = merged
                        dirty.append('persona')
                for field in ['interests_updated_at', 'personas_updated_at']:
                    if getattr(live, field) is None and p.get(field) is not None:
                        setattr(live, field, p[field])
                        dirty.append(field)
                for field in _PROFILE_SCALAR_FIELDS:
                    if getattr(live, field) in (None, '') and p.get(field) not in (None, ''):
                        setattr(live, field, p[field])
                        dirty.append(field)
                if dirty:
                    live.save(update_fields=list(set(dirty)) + ['updated_at'])
                    n_profile += 1

        self.stdout.write(self.style.SUCCESS(
            f'  Restored {n_interest} interest links, {n_chip} custom chips, '
            f'{n_profile} profiles updated.'
        ))

    # ------------------------------------------------------------------ #
    # Restore steps — engagement                                           #
    # ------------------------------------------------------------------ #

    def _restore_comments(self, data, user_map, note_id_map, response_id_map,
                          checkin_id_map, entry_id_map):
        """Recreate comments (incl. nested replies) onto restored targets.

        Processed in ascending backup-id order so a reply's parent comment is
        always remapped before the reply itself. Returns {backup_comment_id:
        new_comment_id}.
        """
        comment_id_map = {}
        cts = data['content_types']
        # model_key -> (id_map, LiveModel); comment map grows as we go.
        dispatch = {
            ('note', 'note'): (note_id_map, Note),
            ('qna', 'response'): (response_id_map, Response),
            ('check_in', 'checkin'): (checkin_id_map, CheckIn),
            ('check_in', 'checkincomponententry'): (entry_id_map, CheckInComponentEntry),
            ('comment', 'comment'): (comment_id_map, Comment),
        }
        ct_cache = {}

        def _resolve(ct_id, obj_id):
            key = cts.get(ct_id)
            if key not in dispatch:
                return None
            id_map, model = dispatch[key]
            new_id = id_map.get(obj_id)
            if new_id is None:
                return None
            if model not in ct_cache:
                ct_cache[model] = ContentType.objects.get_for_model(model)
            return ct_cache[model], new_id

        created = 0
        with transaction.atomic():
            for c in sorted(data['comments'], key=lambda r: r['id']):
                live = user_map.get(c['author_id'])
                if live is None:
                    continue
                if not (c['content'] or '').strip():
                    continue  # AdoorModel requires content length >= 1
                resolved = _resolve(c['content_type_id'], c['object_id'])
                if resolved is None:
                    continue
                live_ct, new_obj_id = resolved
                cm = Comment.objects.create(
                    author=live, content=c['content'],
                    is_private=bool(c['is_private']),
                    content_type=live_ct, object_id=new_obj_id,
                )
                self._set_created_at(Comment, cm.pk, c['created_at'])
                comment_id_map[c['id']] = cm.pk
                created += 1
        self.stdout.write(self.style.SUCCESS(f'  Restored {created} comments.'))
        return comment_id_map

    @staticmethod
    def _target_resolver(content_types, target_maps):
        ct_cache = {}

        def _resolve(ct_id, obj_id):
            key = content_types.get(ct_id)
            if key not in target_maps:
                return None
            id_map, model = target_maps[key]
            new_id = id_map.get(obj_id)
            if new_id is None:
                return None
            if model not in ct_cache:
                ct_cache[model] = ContentType.objects.get_for_model(model)
            return ct_cache[model], new_id

        return _resolve

    def _restore_likes(self, data, user_map, target_maps):
        resolve = self._target_resolver(data['content_types'], target_maps)
        created = 0
        with transaction.atomic():
            for l in data['likes']:
                live = user_map.get(l['user_id'])
                if live is None:
                    continue
                resolved = resolve(l['content_type_id'], l['object_id'])
                if resolved is None:
                    continue
                live_ct, new_obj_id = resolved
                lk = Like.objects.create(
                    user=live, content_type=live_ct, object_id=new_obj_id,
                )
                self._set_created_at(Like, lk.pk, l['created_at'])
                created += 1
        self.stdout.write(self.style.SUCCESS(f'  Restored {created} likes.'))

    def _restore_reactions(self, data, user_map, target_maps):
        resolve = self._target_resolver(data['content_types'], target_maps)
        created = 0
        with transaction.atomic():
            for rx in data['reactions']:
                live = user_map.get(rx['user_id'])
                if live is None:
                    continue
                resolved = resolve(rx['content_type_id'], rx['object_id'])
                if resolved is None:
                    continue
                live_ct, new_obj_id = resolved
                react = Reaction.objects.create(
                    user=live, emoji=rx['emoji'], component=rx['component'],
                    content_type=live_ct, object_id=new_obj_id,
                )
                self._set_created_at(Reaction, react.pk, rx['created_at'])
                created += 1
        self.stdout.write(self.style.SUCCESS(f'  Restored {created} reactions.'))

    def _restore_readers(self, data, user_map, note_id_map, response_id_map, checkin_id_map):
        """Re-link readers M2M for restored Notes/Responses/CheckIns."""
        specs = [
            ('note', Note, note_id_map),
            ('response', Response, response_id_map),
            ('checkin', CheckIn, checkin_id_map),
        ]
        total = 0
        for key, model, id_map in specs:
            through = model.readers.through
            src_col = f'{model._meta.model_name}_id'
            objs = []
            for src_id, uid in data['readers'].get(key, []):
                new_id = id_map.get(src_id)
                live = user_map.get(uid)
                if new_id and live:
                    objs.append(through(**{src_col: new_id, 'user_id': live.id}))
            if objs:
                through.objects.bulk_create(objs, ignore_conflicts=True)
                total += len(objs)
        self.stdout.write(self.style.SUCCESS(f'  Restored {total} reader links.'))

    # ------------------------------------------------------------------ #
    # Discover feed                                                        #
    # ------------------------------------------------------------------ #

    def _regen_discover_feeds(self):
        from account.models import DiscoverFeed, DiscoverFeedMusic
        from account.views import DiscoverFeedView

        DiscoverFeed.objects.filter(user__current_ver='version_q').delete()
        DiscoverFeedMusic.objects.filter(user__current_ver='version_q').delete()

        view = DiscoverFeedView()
        batch_time = timezone.now()
        w_users = list(
            User.objects.filter(
                is_active=True, deleted__isnull=True, current_ver='version_w',
            )
        )
        for user in w_users:
            view.generate_new_feed(user, batch_time=batch_time)
        return len(w_users)
