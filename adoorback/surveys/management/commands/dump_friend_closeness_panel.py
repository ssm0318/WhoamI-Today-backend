"""Dump per-(evaluator, evaluated_user) longitudinal closeness panel as CSV.

Joins three sources at analysis time:
  - FriendEvaluation (per-friend baseline collected at friend-request time)
  - phase1_friend_closeness_part2 SurveyAnswer rows when present, otherwise
    phase1_friend_closeness SurveyAnswer rows (Day 15)
  - phase2_friend_closeness SurveyAnswer rows (Day 28)

Each output row is one (evaluator, evaluated_user) pair with the baseline
plus whatever phase1 / phase2 answers exist. Missing values render as empty
strings so the CSV imports cleanly into pandas / R without parse errors.

Usage:
  python manage.py dump_friend_closeness_panel
  python manage.py dump_friend_closeness_panel --user adoor_1
  python manage.py dump_friend_closeness_panel --out /tmp/panel.csv

The dump is intentionally tolerant of missing data: a friend pair with a
baseline but no phase answers shows up; a phase answer with no matching
baseline (e.g., friend added after baseline window) also shows up. The
analysis code filters down to whatever it needs from there.
"""
from __future__ import annotations

import csv
import sys
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from account.models import FriendEvaluation, User
from surveys.models import (
    PER_FRIEND_TYPES, Survey, SurveyAnswer, SurveyQuestion, SurveyResponse,
)


PHASE_SURVEY_SLUGS = {
    # Part 2 is a clean resubmit of Phase 1 with the corrected prompt/UI, so it
    # supersedes the original response for analysis when both exist.
    1: ('phase1_friend_closeness_part2', 'phase1_friend_closeness'),
    2: ('phase2_friend_closeness',),
}

# Question-slug suffixes that we surface as separate columns in the CSV.
# The slug prefix is the survey slug, so phase1_friend_closeness_current
# / phase2_friend_closeness_current map to the same logical column
# "current_closeness" with a phase suffix in the CSV header.
COLUMN_SUFFIXES = ('current', 'corrected_baseline', 'offline')


class Command(BaseCommand):
    help = (
        'Emit a CSV joining FriendEvaluation baselines with phase1 + phase2 '
        'closeness re-rating answers, one row per (evaluator, evaluated_user).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            help='Limit to a single evaluator (Adoor username). Without this '
                 'flag every user with at least one row in either table is included.',
        )
        parser.add_argument(
            '--out',
            help='Output CSV path. Default: stdout.',
        )

    def handle(self, *args, **opts):
        user_filter: Optional[str] = opts.get('user')
        out_path: Optional[str] = opts.get('out')

        evaluator_qs = User.objects.all()
        if user_filter:
            evaluator_qs = evaluator_qs.filter(username=user_filter)
            if not evaluator_qs.exists():
                raise CommandError(f'No user named {user_filter!r}')

        phase_surveys = {}
        questions_by_phase: dict[int, dict[int, dict[str, SurveyQuestion]]] = {}
        for phase, slugs in PHASE_SURVEY_SLUGS.items():
            by_slug = {
                survey.slug: survey
                for survey in Survey.objects.filter(slug__in=slugs).prefetch_related('questions')
            }
            missing = [slug for slug in slugs if slug not in by_slug]
            for slug in missing:
                self.stderr.write(
                    f'warning: {slug} survey not loaded; it will be skipped for phase {phase}'
                )
            ordered_surveys = [by_slug[slug] for slug in slugs if slug in by_slug]
            phase_surveys[phase] = ordered_surveys
            questions_by_phase[phase] = {
                survey.id: {q.slug: q for q in survey.questions.all()}
                for survey in ordered_surveys
            }

        out_stream = sys.stdout
        out_file = None
        if out_path:
            out_file = open(out_path, 'w', newline='')
            out_stream = out_file

        try:
            writer = csv.writer(out_stream)
            writer.writerow([
                'evaluator_id', 'evaluator_username',
                'evaluated_user_id', 'evaluated_user_username',
                'baseline_closeness', 'baseline_relationship_type',
                'baseline_context', 'baseline_created_at',
                'phase1_current_closeness',
                'phase1_corrected_baseline_closeness',
                'phase1_offline_frequency',
                'phase2_current_closeness',
                'phase2_corrected_baseline_closeness',
                'phase2_offline_frequency',
            ])

            for evaluator in evaluator_qs.iterator():
                row_count = self._emit_evaluator_rows(
                    writer, evaluator, phase_surveys, questions_by_phase,
                )
                if row_count:
                    self.stdout.write(
                        f'{evaluator.username}: {row_count} pair rows',
                        ending='\n',
                    ) if out_path else None
        finally:
            if out_file is not None:
                out_file.close()

    def _emit_evaluator_rows(
        self, writer, evaluator, phase_surveys, questions_by_phase,
    ) -> int:
        """Write all (evaluator → evaluated_user) rows for one evaluator.

        Returns the count for stdout reporting. The set of evaluated_users
        is the union of (a) every user evaluator has a FriendEvaluation row
        for and (b) every user evaluator targeted in either phase survey —
        so post-hoc unfriends still surface.
        """
        baselines = self._latest_baselines(evaluator)
        phase_answers = {
            phase: self._answers_by_target(
                evaluator,
                phase_surveys.get(phase),
                questions_by_phase.get(phase, {}),
            )
            for phase in PHASE_SURVEY_SLUGS
        }

        target_ids: set[int] = set(baselines.keys())
        for answers in phase_answers.values():
            target_ids.update(answers.keys())
        if not target_ids:
            return 0

        targets = {
            u.id: u for u in
            User.objects.filter(id__in=target_ids).only('id', 'username')
        }

        row_count = 0
        for tid in sorted(target_ids):
            target = targets.get(tid)
            baseline = baselines.get(tid)
            p1 = phase_answers[1].get(tid, {})
            p2 = phase_answers[2].get(tid, {})
            writer.writerow([
                evaluator.id, evaluator.username,
                tid, target.username if target else '',
                _maybe(baseline, 'closeness'),
                _maybe(baseline, 'relationship_type'),
                _maybe(baseline, 'context'),
                _maybe(baseline, 'created_at'),
                p1.get('current', ''),
                p1.get('corrected_baseline', ''),
                p1.get('offline', ''),
                p2.get('current', ''),
                p2.get('corrected_baseline', ''),
                p2.get('offline', ''),
            ])
            row_count += 1
        return row_count

    def _latest_baselines(self, evaluator) -> dict[int, FriendEvaluation]:
        """{evaluated_user_id → most recent non-skipped FriendEvaluation}.

        Mirrors the lookup the survey serializer does, so what shows up in
        the CSV's `baseline_closeness` column matches what the participant
        saw inline when they filled out the survey.
        """
        result: dict[int, FriendEvaluation] = {}
        qs = (
            FriendEvaluation.objects
            .filter(evaluator=evaluator, skipped=False)
            .order_by('-created_at')
        )
        for ev in qs:
            result.setdefault(ev.evaluated_user_id, ev)
        return result

    def _answers_by_target(
        self, evaluator, surveys, questions_by_survey,
    ) -> dict[int, dict[str, object]]:
        """{target_user_id → {column_suffix → answer.value}}.

        Empty when the user has no response for any preferred survey. When
        multiple survey slugs are configured for a phase, the first one with
        a response wins.
        """
        if not surveys:
            return {}
        response = None
        slug_to_question = {}
        for survey in surveys:
            slug_to_question = questions_by_survey.get(survey.id, {})
            if not slug_to_question:
                continue
            response = (
                SurveyResponse.objects
                .filter(survey=survey, user=evaluator)
                .order_by('-submitted_at', '-id')
                .first()
            )
            if response is not None:
                break
        if response is None:
            return {}
        result: dict[int, dict[str, object]] = {}
        rows = (
            SurveyAnswer.objects
            .filter(
                response=response,
                question__type__in=PER_FRIEND_TYPES,
                target_user__isnull=False,
            )
            .select_related('question')
        )
        for row in rows:
            suffix = _column_suffix(row.question.slug)
            if suffix is None:
                continue
            target_id = row.target_user_id
            result.setdefault(target_id, {})[suffix] = row.value
        return result


def _column_suffix(question_slug: str) -> Optional[str]:
    """Map question slug to one of COLUMN_SUFFIXES, or None if not relevant.

    phase1_friend_closeness_current              → 'current'
    phase1_friend_closeness_part2_current        → 'current'
    phase2_friend_closeness_corrected_baseline   → 'corrected_baseline'
    phase2_friend_closeness_offline              → 'offline'
    """
    for suffix in COLUMN_SUFFIXES:
        if question_slug.endswith(f'_{suffix}'):
            return suffix
    return None


def _maybe(obj, attr: str) -> str:
    """Stringify an attr on an optional object; empty string when missing."""
    if obj is None:
        return ''
    value = getattr(obj, attr, None)
    if value is None:
        return ''
    return str(value)
