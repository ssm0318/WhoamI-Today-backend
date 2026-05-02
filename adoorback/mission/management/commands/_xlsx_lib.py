"""Pure-Python xlsx parse + validate for Mission content authoring.

Importable without Django so the GitHub Action runner can validate xlsx files
before SSHing to EC2 to mutate the DB.

CLI entrypoint:
    python -m mission.management.commands._xlsx_lib --validate <path>

exits 0 on success, 1 on validation errors with line-numbered output.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any


HEADER_FIELDS = ['status', 'slug', 'prompt_en', 'prompt_ko', 'type']
STATUS_VALUES = {'added', 'modified', 'removed', 'unchanged'}
TYPE_VALUES = {'song', 'question', 'text', 'compliment'}
SLUG_RE = re.compile(r'^[a-z0-9_-]{1,64}$')


def parse_xlsx(path: str | Path) -> list[dict[str, Any]]:
    """Read xlsx at path, return list of row dicts (1 dict per data row).

    Each dict has keys from HEADER_FIELDS plus `_row_num` (1-indexed sheet row).
    The first sheet is read; sheet name is not enforced (xlsx editing tools
    sometimes rename sheets).
    """
    from openpyxl import load_workbook

    wb = load_workbook(filename=str(path), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    header = [str(c).strip().lower() if c is not None else '' for c in rows[0]]
    data: list[dict[str, Any]] = []
    for i, row in enumerate(rows[1:], start=2):
        if all(cell is None or (isinstance(cell, str) and not cell.strip()) for cell in row):
            continue
        rec: dict[str, Any] = {'_row_num': i}
        for col_idx, name in enumerate(header):
            if name in HEADER_FIELDS:
                value = row[col_idx] if col_idx < len(row) else None
                rec[name] = '' if value is None else str(value).strip()
        for f in HEADER_FIELDS:
            rec.setdefault(f, '')
        status = rec['status'].lower()
        rec['status'] = status if status else 'unchanged'
        data.append(rec)
    return data


def validate_rows(rows: list[dict[str, Any]]) -> list[tuple[int, str]]:
    """Return list of (row_num, message) tuples; empty list = valid."""
    errors: list[tuple[int, str]] = []
    seen_slugs: dict[str, int] = {}

    for rec in rows:
        rn = rec['_row_num']
        status = rec['status']
        if status not in STATUS_VALUES:
            errors.append((rn, f'invalid status {status!r}; must be one of {sorted(STATUS_VALUES)}'))
            continue

        slug = rec['slug']
        if not slug:
            errors.append((rn, 'slug is required'))
            continue
        if not SLUG_RE.match(slug):
            errors.append((rn, f'invalid slug {slug!r}; must match [a-z0-9_-], max 64 chars'))
        if slug in seen_slugs:
            errors.append((rn, f'duplicate slug {slug!r} (also on row {seen_slugs[slug]})'))
        else:
            seen_slugs[slug] = rn

        if status in {'added', 'modified'}:
            if not rec['prompt_en']:
                errors.append((rn, f'prompt_en is required for status={status!r}'))
            if rec['type'] not in TYPE_VALUES:
                errors.append((rn, f'invalid type {rec["type"]!r}; must be one of {sorted(TYPE_VALUES)}'))

    return errors


def _validate_cli(path: str) -> int:
    p = Path(path)
    if not p.is_file():
        print(f'ERROR: file not found: {path}', file=sys.stderr)
        return 1
    try:
        rows = parse_xlsx(p)
    except Exception as e:
        print(f'ERROR: failed to parse {path}: {e}', file=sys.stderr)
        return 1
    errors = validate_rows(rows)
    if errors:
        print(f'Validation FAILED on {path} ({len(errors)} error(s)):', file=sys.stderr)
        for rn, msg in errors:
            print(f'  row {rn}: {msg}', file=sys.stderr)
        return 1
    print(f'OK: {path} ({len(rows)} data rows)')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Validate or inspect a Mission xlsx file.')
    parser.add_argument('--validate', metavar='PATH', help='Validate the xlsx file at PATH and exit.')
    args = parser.parse_args(argv)
    if args.validate:
        return _validate_cli(args.validate)
    parser.print_help()
    return 2


if __name__ == '__main__':
    sys.exit(main())
