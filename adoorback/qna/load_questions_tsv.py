"""
Load admin questions from questions.tsv (content_en / content_ko columns).

Used by management command load_questions and by test seed data.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Tuple

from django.conf import settings

from qna.models import Question


def questions_tsv_path(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit)
    return Path(settings.BASE_DIR) / "assets" / "questions.tsv"


def iter_tsv_rows(path: Path) -> Iterable[Tuple[str, str, str]]:
    """
    Yield (content, content_en, content_ko) for each data row.
    `content` is the canonical AdoorModel text (English preferred).
    """
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            en = (row.get("content_en") or "").strip()
            ko = (row.get("content_ko") or "").strip()
            if not en and not ko:
                continue
            content = en or ko
            yield content, en or content, ko or content


def bulk_create_questions_from_tsv(
    admin,
    *,
    path: str | Path | None = None,
    skip_duplicates: bool = False,
) -> tuple[int, str]:
    """
    Create Question rows from TSV. Returns (created_count, status).

    status is one of: 'ok', 'missing_file', 'nothing_new'
    """
    tsv_path = questions_tsv_path(path)
    if not tsv_path.is_file():
        return 0, "missing_file"

    existing: set[tuple[str, str]] = set()
    if skip_duplicates:
        existing = set(
            Question.objects.filter(
                author=admin, is_admin_question=True
            ).values_list("content_en", "content_ko")
        )

    to_create: list[Question] = []
    for content, en, ko in iter_tsv_rows(tsv_path):
        if skip_duplicates and (en, ko) in existing:
            continue
        if skip_duplicates:
            existing.add((en, ko))
        to_create.append(
            Question(
                author=admin,
                is_admin_question=True,
                content=content,
                content_en=en,
                content_ko=ko,
            )
        )

    if not to_create:
        return 0, "nothing_new"

    Question.objects.bulk_create(to_create, batch_size=500)
    return len(to_create), "ok"
