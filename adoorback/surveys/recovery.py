from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from django.contrib.auth import get_user_model
from django.utils import timezone

from surveys.models import (
    INPUT_LESS_TYPES, ScheduledSurvey, SurveyAnswer, SurveyQuestion, SurveyResponse,
)


DEFAULT_RECOVERY_MANIFEST_PATH = Path(__file__).resolve().parent / 'fixtures' / 'recovery_question_map.yaml'
MERGEABLE_EQUIVALENCE = frozenset({'exact', 'compatible'})


def load_recovery_manifest(path: str | Path | None = None) -> dict[str, Any]:
    manifest_path = Path(path) if path else DEFAULT_RECOVERY_MANIFEST_PATH
    return _load_recovery_manifest_cached(str(manifest_path), manifest_path.stat().st_mtime_ns)


@lru_cache(maxsize=8)
def _load_recovery_manifest_cached(path: str, _mtime_ns: int) -> dict[str, Any]:
    manifest_path = Path(path)
    with manifest_path.open(encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f'Recovery manifest must be a mapping: {manifest_path}')
    data['_manifest_path'] = str(manifest_path)
    return data


def build_recovery_coverage(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    manifest = manifest or load_recovery_manifest()
    canonical_by_id = {
        item['canonical_id']: item
        for item in manifest.get('canonical_questions', [])
    }
    report = {
        'generated_at': timezone.now().isoformat(),
        'manifest_path': manifest.get('_manifest_path', ''),
        'canonical_question_count': len(canonical_by_id),
        'recovery_surveys': [],
        'warnings': [],
    }

    for recovery in manifest.get('recovery_surveys', []):
        eligible_users = _eligible_users(recovery.get('eligible_if', {}))
        canonical_reports = []
        users_needing_recovery = set()
        missing_canonical_ids_by_user_id: dict[int, list[str]] = defaultdict(list)
        related_only_canonical_ids_by_user_id: dict[int, list[str]] = defaultdict(list)

        for canonical_id in recovery.get('collects_canonical_ids', []):
            canonical = canonical_by_id.get(canonical_id)
            if canonical is None:
                report['warnings'].append({
                    'type': 'unknown_canonical_id',
                    'recovery_survey_slug': recovery.get('survey_slug', ''),
                    'canonical_id': canonical_id,
                })
                continue

            exact_answers = _answers_for_sources(canonical.get('sources', []), mergeable_only=True)
            related_answers = _answers_for_sources(
                canonical.get('related_sources', []),
                mergeable_only=False,
            )
            answered_user_ids = set(exact_answers.keys())
            related_user_ids = set(related_answers.keys())
            eligible_user_ids = {u.id for u in eligible_users}
            missing_user_ids = eligible_user_ids - answered_user_ids
            users_needing_recovery.update(missing_user_ids)
            for user_id in missing_user_ids:
                missing_canonical_ids_by_user_id[user_id].append(canonical_id)
            for user_id in related_user_ids & eligible_user_ids:
                if user_id not in answered_user_ids:
                    related_only_canonical_ids_by_user_id[user_id].append(canonical_id)

            canonical_reports.append({
                'canonical_id': canonical_id,
                'response_type': canonical.get('response_type', ''),
                'eligible_user_count': len(eligible_user_ids),
                'answered_user_count': len(answered_user_ids & eligible_user_ids),
                'missing_user_count': len(missing_user_ids),
                'related_only_user_count': len(related_user_ids & eligible_user_ids),
                'answered_usernames': _usernames_for_ids(answered_user_ids & eligible_user_ids),
                'missing_usernames': _usernames_for_ids(missing_user_ids),
                'related_only_usernames': _usernames_for_ids(related_user_ids & eligible_user_ids),
                'sources': _source_status(canonical.get('sources', [])),
                'related_sources': _source_status(canonical.get('related_sources', [])),
            })

        report['recovery_surveys'].append({
            'survey_slug': recovery.get('survey_slug', ''),
            'participant_title': recovery.get('participant_title', ''),
            'base_survey_slug': recovery.get('base_survey_slug', ''),
            'eligible_user_count': len(eligible_users),
            'eligible_usernames': [u.username for u in eligible_users],
            'users_needing_recovery_count': len(users_needing_recovery),
            'users_needing_recovery_usernames': _usernames_for_ids(users_needing_recovery),
            'missing_canonical_ids_by_username': _canonical_ids_by_username(
                missing_canonical_ids_by_user_id,
            ),
            'related_only_canonical_ids_by_username': _canonical_ids_by_username(
                related_only_canonical_ids_by_user_id,
            ),
            'canonical_questions': canonical_reports,
        })

    return report


def recovery_definition_for_survey_slug(
    survey_slug: str,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    manifest = manifest or load_recovery_manifest()
    for recovery in manifest.get('recovery_surveys', []):
        if recovery.get('survey_slug') == survey_slug:
            return recovery
    return None


def is_recovery_survey_slug(survey_slug: str, manifest: dict[str, Any] | None = None) -> bool:
    return recovery_definition_for_survey_slug(survey_slug, manifest) is not None


def missing_recovery_question_slugs_for_user(user, survey, manifest: dict[str, Any] | None = None) -> set[str] | None:
    """Return visible question slugs for a recovery survey, or None for non-recovery surveys.

    Recovery survey rows contain every possible recovery question, but a
    participant should only see the subset of canonical final-schema questions
    they have not already answered through an exact/compatible source.
    """
    manifest = manifest or load_recovery_manifest()
    recovery = recovery_definition_for_survey_slug(survey.slug, manifest)
    if recovery is None:
        return None
    if _user_should_answer_full_recovery(user, recovery):
        return _all_input_question_slugs(survey)
    if not _user_matches_recovery_rule(user, recovery.get('eligible_if', {})):
        return set()
    if recovery.get('full_resubmit_until_answered'):
        if SurveyResponse.objects.filter(user=user, survey=survey).exists():
            return set()
        return _all_input_question_slugs(survey)

    canonical_by_id = {
        item['canonical_id']: item
        for item in manifest.get('canonical_questions', [])
    }
    visible_slugs: set[str] = set()
    for canonical_id in recovery.get('collects_canonical_ids', []):
        canonical = canonical_by_id.get(canonical_id)
        if canonical is None:
            continue
        if _user_has_mergeable_answer_for_sources(user, canonical.get('sources', [])):
            continue
        for source in canonical.get('sources', []):
            if source.get('equivalence') not in MERGEABLE_EQUIVALENCE:
                continue
            if source.get('survey_slug') == survey.slug:
                question_slug = source.get('question_slug', '')
                if question_slug:
                    visible_slugs.add(question_slug)
    return _expand_feature_recovery_blocks(survey, visible_slugs)


def _feature_block_root_slug(question_slug: str) -> str:
    root_slug = question_slug
    for suffix in ('_enjoy', '_dislike'):
        if root_slug.endswith(suffix):
            root_slug = root_slug[:-len(suffix)]
            break
    if root_slug.startswith('goal') and '_feat_' in root_slug:
        return root_slug
    return ''


def _expand_feature_recovery_blocks(survey, visible_slugs: set[str]) -> set[str]:
    block_roots = {
        root_slug
        for root_slug in (_feature_block_root_slug(slug) for slug in visible_slugs)
        if root_slug
    }
    if not block_roots:
        return visible_slugs

    block_slugs = set()
    for root_slug in block_roots:
        block_slugs.update({root_slug, f'{root_slug}_enjoy', f'{root_slug}_dislike'})

    existing_block_slugs = set(
        SurveyQuestion.objects
        .filter(survey=survey, slug__in=block_slugs)
        .exclude(type__in=INPUT_LESS_TYPES)
        .values_list('slug', flat=True)
    )
    return visible_slugs | existing_block_slugs


def missing_recovery_question_ids_for_user(user, survey) -> set[int] | None:
    slugs = missing_recovery_question_slugs_for_user(user, survey)
    if slugs is None:
        return None
    if not slugs:
        return set()
    return set(
        SurveyQuestion.objects
        .filter(survey=survey, slug__in=slugs)
        .exclude(type__in=INPUT_LESS_TYPES)
        .values_list('id', flat=True)
    )


def recovery_survey_has_visible_questions_for_user(user, survey) -> bool:
    question_ids = missing_recovery_question_ids_for_user(user, survey)
    if question_ids is None:
        return True
    return bool(question_ids)


def replacement_recovery_slug_for_base_unanswered(user, base_survey) -> str | None:
    """Return the replacement Part survey slug for an unanswered base survey.

    This is an index-level routing helper: old base rows are hidden when a
    replacement container exists, but direct old-survey URLs/submits remain
    allowed so stale in-progress sessions do not lose their answers.
    """
    manifest = load_recovery_manifest()
    if SurveyResponse.objects.filter(user=user, survey=base_survey).exists():
        return None
    for recovery in manifest.get('recovery_surveys', []):
        if recovery.get('base_survey_slug') != base_survey.slug:
            continue
        if not recovery.get('replace_base_if_unanswered'):
            continue
        if not _user_matches_recovery_rule(
            user,
            recovery.get('eligible_if', {}),
            require_answered=False,
        ):
            continue
        recovery_slug = recovery.get('survey_slug', '')
        if recovery_slug and ScheduledSurvey.objects.filter(survey__slug=recovery_slug).exists():
            return recovery_slug
    return None


def _user_should_answer_full_recovery(user, recovery: dict[str, Any]) -> bool:
    base_slug = recovery.get('base_survey_slug', '')
    if not base_slug or not recovery.get('show_all_if_base_unanswered'):
        return False
    if not _user_matches_recovery_rule(
        user,
        recovery.get('eligible_if', {}),
        require_answered=False,
    ):
        return False
    return not SurveyResponse.objects.filter(user=user, survey__slug=base_slug).exists()


def _all_input_question_slugs(survey) -> set[str]:
    return set(
        survey.questions
        .exclude(type__in=INPUT_LESS_TYPES)
        .values_list('slug', flat=True)
    )


def _eligible_users(rule: dict[str, Any]):
    User = get_user_model()
    qs = User.objects.filter(is_active=True, is_staff=False).order_by('username', 'id')
    user_group = rule.get('user_group')
    if user_group:
        qs = qs.filter(user_group=user_group)

    answered_survey_slug = rule.get('answered_survey_slug')
    if answered_survey_slug:
        user_ids = (
            SurveyResponse.objects
            .filter(survey__slug=answered_survey_slug)
            .values_list('user_id', flat=True)
            .distinct()
        )
        qs = qs.filter(id__in=user_ids)
    return list(qs)


def _user_matches_recovery_rule(
    user,
    rule: dict[str, Any],
    *,
    require_answered: bool = True,
) -> bool:
    if not getattr(user, 'is_active', False) or getattr(user, 'is_staff', False):
        return False
    user_group = rule.get('user_group')
    if user_group and getattr(user, 'user_group', '') != user_group:
        return False
    answered_survey_slug = rule.get('answered_survey_slug')
    if require_answered and answered_survey_slug and not SurveyResponse.objects.filter(
        user=user,
        survey__slug=answered_survey_slug,
    ).exists():
        return False
    return True


def _user_has_mergeable_answer_for_sources(user, sources: list[dict[str, Any]]) -> bool:
    return any(_answers_for_sources(sources, mergeable_only=True, user=user).values())


def _answers_for_sources(
    sources: list[dict[str, Any]],
    *,
    mergeable_only: bool,
    user=None,
) -> dict[int, list[SurveyAnswer]]:
    grouped: dict[int, list[SurveyAnswer]] = defaultdict(list)
    for source in sources:
        equivalence = source.get('equivalence', '')
        if mergeable_only and equivalence not in MERGEABLE_EQUIVALENCE:
            continue
        answers = SurveyAnswer.objects.filter(
            question__survey__slug=source.get('survey_slug', ''),
            question__slug=source.get('question_slug', ''),
        )
        if user is not None:
            answers = answers.filter(response__user=user)
        answers = (
            answers
            .select_related('response__user', 'question__survey', 'question')
            .order_by('response__user__username', '-response__submitted_at', '-id')
        )
        for answer in answers:
            if _value_is_excluded(answer.value, source.get('exclude_values', [])):
                continue
            grouped[answer.response.user_id].append(answer)
    return grouped


def _source_status(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    status = []
    for source in sources:
        survey_slug = source.get('survey_slug', '')
        question_slug = source.get('question_slug', '')
        exists = SurveyQuestion.objects.filter(
            survey__slug=survey_slug,
            slug=question_slug,
        ).exists()
        answer_count = SurveyAnswer.objects.filter(
            question__survey__slug=survey_slug,
            question__slug=question_slug,
        ).count()
        excluded_answer_count = sum(
            1
            for value in SurveyAnswer.objects
            .filter(
                question__survey__slug=survey_slug,
                question__slug=question_slug,
            )
            .values_list('value', flat=True)
            if _value_is_excluded(value, source.get('exclude_values', []))
        )
        status.append({
            'survey_slug': survey_slug,
            'question_slug': question_slug,
            'equivalence': source.get('equivalence', ''),
            'exists_in_db': exists,
            'answer_count': answer_count,
            'excluded_answer_count': excluded_answer_count,
            'exclude_values': source.get('exclude_values', []),
            'reason': source.get('reason', ''),
        })
    return status


def _value_is_excluded(value: Any, excluded_values: list[Any]) -> bool:
    return any(value == excluded for excluded in excluded_values)


def _usernames_for_ids(user_ids: set[int]) -> list[str]:
    if not user_ids:
        return []
    User = get_user_model()
    return list(
        User.objects
        .filter(id__in=user_ids)
        .order_by('username', 'id')
        .values_list('username', flat=True)
    )


def _canonical_ids_by_username(canonical_ids_by_user_id: dict[int, list[str]]) -> dict[str, list[str]]:
    if not canonical_ids_by_user_id:
        return {}
    User = get_user_model()
    users = (
        User.objects
        .filter(id__in=canonical_ids_by_user_id.keys())
        .order_by('username', 'id')
    )
    return {
        user.username: sorted(canonical_ids_by_user_id[user.id])
        for user in users
    }
