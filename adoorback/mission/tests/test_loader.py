from datetime import date
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from openpyxl import Workbook

from mission.models import Mission


def _write_xlsx(rows, *, headers=None) -> Path:
    """Write a temp xlsx file and return its path."""
    headers = headers or ['status', 'slug', 'prompt_en', 'prompt_ko', 'type']
    wb = Workbook()
    ws = wb.active
    ws.title = 'Missions'
    ws.append(headers)
    for r in rows:
        ws.append(list(r))
    out = Path(settings.BASE_DIR) / 'assets' / '_test_missions_tmp.xlsx'
    wb.save(out)
    return out


class LoadMissionsXlsxTest(TestCase):
    def tearDown(self):
        tmp = Path(settings.BASE_DIR) / 'assets' / '_test_missions_tmp.xlsx'
        if tmp.exists():
            tmp.unlink()

    def test_dry_run_no_writes(self):
        path = _write_xlsx([
            ('added', 'm_test_dry', 'Hello', '안녕', 'text'),
        ])
        call_command('load_missions_xlsx', f'--path={path}', '--dry-run')
        self.assertEqual(Mission.objects.filter(slug='m_test_dry').count(), 0)

    def test_added_creates_row(self):
        path = _write_xlsx([
            ('added', 'm_test_add', 'Hello', '안녕', 'text'),
        ])
        call_command('load_missions_xlsx', f'--path={path}')
        m = Mission.objects.get(slug='m_test_add')
        self.assertEqual(m.prompt_en, 'Hello')
        self.assertEqual(m.prompt_ko, '안녕')
        self.assertEqual(m.type, 'text')
        self.assertEqual(m.selected_dates, [])
        self.assertFalse(m.selected)

    def test_modified_updates_row(self):
        Mission.objects.create(
            slug='m_test_mod', prompt_en='old', prompt_ko='', type='text',
        )
        path = _write_xlsx([
            ('modified', 'm_test_mod', 'new', 'new-ko', 'song'),
        ])
        call_command('load_missions_xlsx', f'--path={path}')
        m = Mission.objects.get(slug='m_test_mod')
        self.assertEqual(m.prompt_en, 'new')
        self.assertEqual(m.prompt_ko, 'new-ko')
        self.assertEqual(m.type, 'song')

    def test_added_idempotent(self):
        path = _write_xlsx([
            ('added', 'm_test_idem', 'Hi', '', 'text'),
        ])
        call_command('load_missions_xlsx', f'--path={path}')
        before = Mission.objects.count()
        call_command('load_missions_xlsx', f'--path={path}')
        after = Mission.objects.count()
        self.assertEqual(before, after)

    def test_removed_deletes_row(self):
        Mission.objects.create(
            slug='m_test_rm', prompt_en='bye', prompt_ko='', type='text',
        )
        path = _write_xlsx([
            ('removed', 'm_test_rm', '', '', ''),
        ])
        call_command('load_missions_xlsx', f'--path={path}')
        self.assertFalse(Mission.objects.filter(slug='m_test_rm').exists())

    def test_removed_blocked_when_scheduled(self):
        Mission.objects.create(
            slug='m_test_rm_sched',
            prompt_en='locked',
            prompt_ko='',
            type='text',
            selected_dates=[date(2026, 5, 3)],
            selected=True,
        )
        path = _write_xlsx([
            ('removed', 'm_test_rm_sched', '', '', ''),
        ])
        with self.assertRaises(CommandError) as ctx:
            call_command('load_missions_xlsx', f'--path={path}')
        self.assertIn('schedule', str(ctx.exception).lower())
        self.assertTrue(Mission.objects.filter(slug='m_test_rm_sched').exists())

    def test_validation_rejects_bad_status(self):
        path = _write_xlsx([
            ('foobar', 'm_test_bad_status', 'x', '', 'text'),
        ])
        with self.assertRaises(CommandError):
            call_command('load_missions_xlsx', f'--path={path}')

    def test_validation_rejects_invalid_slug(self):
        path = _write_xlsx([
            ('added', 'BAD SLUG', 'x', '', 'text'),
        ])
        with self.assertRaises(CommandError):
            call_command('load_missions_xlsx', f'--path={path}')

    def test_validation_rejects_duplicate_slug(self):
        path = _write_xlsx([
            ('added', 'm_test_dup', 'x', '', 'text'),
            ('added', 'm_test_dup', 'y', '', 'text'),
        ])
        with self.assertRaises(CommandError):
            call_command('load_missions_xlsx', f'--path={path}')

    def test_validation_rejects_missing_prompt_en(self):
        path = _write_xlsx([
            ('added', 'm_test_noprompt', '', '', 'text'),
        ])
        with self.assertRaises(CommandError):
            call_command('load_missions_xlsx', f'--path={path}')

    def test_validation_rejects_invalid_type(self):
        path = _write_xlsx([
            ('added', 'm_test_badtype', 'x', '', 'invalid'),
        ])
        with self.assertRaises(CommandError):
            call_command('load_missions_xlsx', f'--path={path}')

    def test_unchanged_is_noop(self):
        Mission.objects.create(
            slug='m_test_unchanged', prompt_en='keep', prompt_ko='', type='text',
        )
        path = _write_xlsx([
            ('unchanged', 'm_test_unchanged', '', '', ''),
        ])
        call_command('load_missions_xlsx', f'--path={path}')
        m = Mission.objects.get(slug='m_test_unchanged')
        self.assertEqual(m.prompt_en, 'keep')
