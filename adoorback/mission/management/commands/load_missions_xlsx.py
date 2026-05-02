"""Load Mission content from an xlsx file.

xlsx columns: status, slug, prompt_en, prompt_ko, type
status enum: added | modified | removed | unchanged (blank = unchanged)
slug is the natural key for the lifecycle.

Removed rows are blocked when the slug has selected_dates entries (i.e., is part
of the curated study schedule) — protects the schedule from accidental damage.
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mission.management.commands._xlsx_lib import parse_xlsx, validate_rows
from mission.models import Mission


def _default_path() -> Path:
    return Path(settings.BASE_DIR) / 'assets' / 'missions.xlsx'


class Command(BaseCommand):
    help = 'Load Mission content from an xlsx file (status-driven upserts/deletes).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            type=str,
            default=None,
            help='Path to the xlsx file. Defaults to <BASE_DIR>/assets/missions.xlsx.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Parse + validate only; no DB writes.',
        )

    def handle(self, *args, **opts):
        path = Path(opts['path']) if opts['path'] else _default_path()
        if not path.is_file():
            raise CommandError(f'xlsx file not found: {path}')

        rows = parse_xlsx(path)
        errors = validate_rows(rows)
        if errors:
            for rn, msg in errors:
                self.stdout.write(self.style.ERROR(f'row {rn}: {msg}'))
            raise CommandError(f'Validation failed: {len(errors)} error(s).')

        if opts['dry_run']:
            self.stdout.write(self.style.SUCCESS(
                f'[DRY RUN] {path} parsed and validated cleanly ({len(rows)} rows).'
            ))
            return

        counts = self._apply(rows)
        self.stdout.write(self.style.SUCCESS(
            f"added:{counts['added']} modified:{counts['modified']} "
            f"removed:{counts['removed']} unchanged:{counts['unchanged']}"
        ))

    @transaction.atomic
    def _apply(self, rows):
        counts = {'added': 0, 'modified': 0, 'removed': 0, 'unchanged': 0}
        for rec in rows:
            rn = rec['_row_num']
            status = rec['status']
            slug = rec['slug']
            if status in ('added', 'modified'):
                _, was_created = Mission.objects.update_or_create(
                    slug=slug,
                    defaults={
                        'prompt_en': rec['prompt_en'],
                        'prompt_ko': rec.get('prompt_ko', ''),
                        'type': rec['type'],
                    },
                )
                counts['added' if was_created else 'modified'] += 1
            elif status == 'removed':
                existing = Mission.objects.filter(slug=slug).first()
                if existing and existing.selected_dates:
                    raise CommandError(
                        f"row {rn}: Cannot remove slug {slug!r}: it is scheduled on "
                        f"dates {existing.selected_dates}. Remove from the schedule "
                        f"migration first."
                    )
                deleted, _ = Mission.objects.filter(slug=slug).delete()
                if deleted == 0:
                    self.stdout.write(self.style.WARNING(
                        f"row {rn}: slug {slug!r} not found (treating as no-op)"
                    ))
                counts['removed'] += 1
            else:
                counts['unchanged'] += 1
        return counts
