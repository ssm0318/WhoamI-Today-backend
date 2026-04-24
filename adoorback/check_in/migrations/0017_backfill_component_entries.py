"""Backfill CheckInComponentEntry rows from existing CheckIn + Song data.

For each non-deleted CheckIn, creates up to three entries (battery, mood,
thought) for the components that have data. For each non-deleted Song,
creates one entry with `{track_id}` as payload; full metadata (title,
artist, album_cover_url) is populated by the save-path change in the
follow-up feat/entry-writes migration and by any future refreshes.

Per-entry `created_at` mirrors the component's `*_updated_at` timestamp
when available (falls back to CheckIn/Song `created_at`). After inserts,
`superseded_at` is assigned per (owner, component) group: the latest row
retains `superseded_at=NULL`; every predecessor is set to the immediately
newer entry's `created_at`.

Reverse hard-deletes all rows from the new table. This is safe because at
this point in the migration history no other code path writes to
`check_in_checkincomponententry` yet; the save-path switch lands in a
later stacked migration.
"""

from collections import defaultdict

from django.db import migrations


def backfill_entries(apps, schema_editor):
    CheckIn = apps.get_model("check_in", "CheckIn")
    Song = apps.get_model("check_in", "Song")
    Entry = apps.get_model("check_in", "CheckInComponentEntry")

    # (owner_id, component, data, visibility, desired_created_at)
    pending = []

    check_ins = CheckIn.objects.filter(deleted__isnull=True).order_by("created_at")

    for ci in check_ins:
        fallback_ts = ci.created_at

        if ci.social_battery:
            pending.append(
                (
                    ci.user_id,
                    "battery",
                    {"social_battery": ci.social_battery},
                    ci.battery_visibility,
                    ci.battery_updated_at or fallback_ts,
                )
            )

        if ci.mood:
            pending.append(
                (
                    ci.user_id,
                    "mood",
                    {"mood": list(ci.mood)},
                    ci.mood_visibility,
                    ci.mood_updated_at or fallback_ts,
                )
            )

        if ci.thought:
            pending.append(
                (
                    ci.user_id,
                    "thought",
                    {"thought": ci.thought},
                    ci.thought_visibility,
                    ci.thought_updated_at or fallback_ts,
                )
            )

    songs = Song.objects.filter(deleted__isnull=True).order_by("created_at")
    for song in songs:
        nearest = (
            CheckIn.objects.filter(
                user_id=song.user_id,
                deleted__isnull=True,
                created_at__lte=song.created_at,
            )
            .order_by("-created_at")
            .first()
        )
        visibility = nearest.song_visibility if nearest else "public"
        pending.append(
            (
                song.user_id,
                "song",
                {"track_id": song.track_id},
                visibility,
                song.created_at,
            )
        )

    if not pending:
        return

    # bulk_create sets auto_now_add's created_at to timezone.now(); we override
    # to the desired historical timestamp immediately after via .update().
    instances = [
        Entry(owner_id=owner_id, component=component, data=data, visibility=visibility)
        for owner_id, component, data, visibility, _ in pending
    ]
    created = Entry.objects.bulk_create(instances, batch_size=500)

    # Stamp created_at to the historical value for each new row.
    for entry, (_, _, _, _, ts) in zip(created, pending):
        Entry.objects.filter(pk=entry.pk).update(created_at=ts)

    # Compute superseded_at per (owner, component) group.
    groups = defaultdict(list)
    for entry, (owner_id, component, _, _, ts) in zip(created, pending):
        groups[(owner_id, component)].append((entry.pk, ts))

    for items in groups.values():
        items.sort(key=lambda pair: pair[1])
        for i in range(len(items) - 1):
            pk = items[i][0]
            next_ts = items[i + 1][1]
            Entry.objects.filter(pk=pk).update(superseded_at=next_ts)


def reverse_backfill(apps, schema_editor):
    Entry = apps.get_model("check_in", "CheckInComponentEntry")
    # Historical model has no safedelete manager: this is a real SQL DELETE.
    Entry.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("check_in", "0016_checkincomponententry"),
    ]

    operations = [
        migrations.RunPython(backfill_entries, reverse_backfill),
    ]
