"""Survey slugs intentionally removed from participant-facing flows."""

RETIRED_SURVEY_SLUGS = frozenset({
    'pre_study',
    'pre_study_catchup',
})


def is_retired_survey_slug(slug: str) -> bool:
    return slug in RETIRED_SURVEY_SLUGS
