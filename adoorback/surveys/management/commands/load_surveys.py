"""Load Survey content from a YAML/JSON fixture.

Two YAML extensions are supported on top of stock anchors/aliases:

  1. The standard `&name` / `*name` for sharing a single mapping.
  2. A custom `_include: <anchor_name>` directive at any list position. The
     loader replaces the entry with the full anchored sequence.

Example:

    _shared_block: &shared_block
      - order: 1
        slug: shared_q1
        ...
      - order: 2
        slug: shared_q2
        ...

    - slug: my_survey
      questions:
        - order: 1
          slug: header
          type: display_only
        - _include: shared_block       # expands to the two questions above
        - order: 99
          slug: my_specific_q
          type: likert_5

After expansion, all `order` numbers are re-assigned based on list position
(post-composition). Authors should still author block-relative orders for
readability, but the absolute numbering is what hits the DB.

`_shared_block` (or any top-level entry whose slug starts with `_`) is
treated as anchor-only — never persisted as a Survey. PyYAML keeps the
anchor live for downstream `*` references, so this is the standard pattern
for "shared bank, not a survey."
"""
from pathlib import Path

import yaml
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from surveys.models import Survey, SurveyOption, SurveyQuestion


# Top-level entries with slugs starting with this prefix are anchor-only and
# not persisted as Surveys. Convention: `_shared_questions`, `_tie_outcomes`, …
ANCHOR_ONLY_SLUG_PREFIX = '_'

# YAML keyword that triggers list expansion. Form: `{ _include: <name> }`
# inside a list of questions or options. The named anchor must point to a
# *list*; its items are spliced into the parent list at the directive's
# position.
INCLUDE_DIRECTIVE = '_include'


class Command(BaseCommand):
    help = (
        'Load survey definitions from a YAML/JSON fixture. '
        'Idempotent on slug: existing surveys are updated; new ones are created. '
        'Supports `_include: <anchor_name>` for splicing shared question banks.'
    )

    def add_arguments(self, parser):
        parser.add_argument('path', help='Path to YAML or JSON fixture file')
        parser.add_argument(
            '--replace-questions',
            action='store_true',
            help='If set, delete existing questions/options for matched surveys before re-creating them.',
        )

    def handle(self, *args, **opts):
        path = Path(opts['path'])
        if not path.exists():
            raise CommandError(f'Fixture not found: {path}')
        text = path.read_text(encoding='utf-8')
        if path.suffix in {'.yaml', '.yml'}:
            anchor_lookup = _load_yaml_with_anchor_lookup(text)
            data = anchor_lookup['data']
            anchors = anchor_lookup['anchors']
        elif path.suffix == '.json':
            import json
            data = json.loads(text)
            anchors = {}
        else:
            raise CommandError(f'Unsupported extension: {path.suffix}')
        if not isinstance(data, list):
            raise CommandError('Top-level fixture must be a list of surveys.')

        loaded = 0
        skipped_anchor_only = 0
        with transaction.atomic():
            for entry in data:
                slug = entry.get('slug', '')
                if slug.startswith(ANCHOR_ONLY_SLUG_PREFIX):
                    skipped_anchor_only += 1
                    continue
                self._upsert(entry, anchors=anchors, replace_questions=opts['replace_questions'])
                loaded += 1
        msg = f'Loaded {loaded} surveys from {path}'
        if skipped_anchor_only:
            msg += f' (skipped {skipped_anchor_only} anchor-only entries)'
        self.stdout.write(self.style.SUCCESS(msg))

    def _upsert(self, entry, *, anchors: dict, replace_questions: bool):
        slug = entry['slug']
        default_type = entry.get('type', SurveyQuestion._meta.get_field('type').default)

        defaults = {
            'title_en': entry['title']['en'],
            'title_ko': entry['title'].get('ko', ''),
            'description_en': entry.get('description', {}).get('en', ''),
            'description_ko': entry.get('description', {}).get('ko', ''),
            'interpretation_en': entry.get('interpretation', {}).get('en', ''),
            'interpretation_ko': entry.get('interpretation', {}).get('ko', ''),
            'friend_visible': entry.get('friend_visible', True),
            'results_hidden': entry.get('results_hidden', False),
            # Long-form study extensions:
            'result_kind': entry.get('result_kind', ''),
            'score_formula': entry.get('score_formula', ''),
            'score_components': entry.get('score_components', []) or [],
            'tokens': entry.get('tokens', {}) or {},
            'repeatable': entry.get('repeatable', False),
            'serving_condition': entry.get('serving_condition', {}) or {},
        }
        survey, created = Survey.objects.update_or_create(slug=slug, defaults=defaults)

        if replace_questions or created:
            survey.questions.all().delete()
            raw_questions = list(entry.get('questions', []))
            expanded = _expand_includes(raw_questions, anchors, context=f'survey {slug!r}')
            self._validate_unique_slugs(expanded, context=f'survey {slug!r}')
            # Order numbers are re-assigned by list position post-composition,
            # so authors can use block-relative ordering and not worry about
            # cross-block collisions.
            for absolute_order, q in enumerate(expanded, start=1):
                question = SurveyQuestion.objects.create(
                    survey=survey,
                    order=absolute_order,
                    type=q.get('type', default_type),
                    prompt_en=q.get('prompt', {}).get('en', ''),
                    prompt_ko=q.get('prompt', {}).get('ko', ''),
                    low_label_en=q.get('low_label', {}).get('en', ''),
                    low_label_ko=q.get('low_label', {}).get('ko', ''),
                    high_label_en=q.get('high_label', {}).get('en', ''),
                    high_label_ko=q.get('high_label', {}).get('ko', ''),
                    reverse_scored=q.get('reverse_scored', False),
                    result_kind=q.get('result_kind', ''),
                    result_group=q.get('result_group', ''),
                    result_hidden=q.get('result_hidden', False),
                    slider_min_value=q.get('slider_min_value'),
                    slider_max_value=q.get('slider_max_value'),
                    # Long-form study extensions:
                    slug=q.get('slug', ''),
                    description_en=q.get('description', {}).get('en', ''),
                    description_ko=q.get('description', {}).get('ko', ''),
                    placeholder_en=q.get('placeholder', {}).get('en', ''),
                    placeholder_ko=q.get('placeholder', {}).get('ko', ''),
                    min_length=q.get('min_length'),
                    min_length_warning_en=q.get('min_length_warning', {}).get('en', ''),
                    min_length_warning_ko=q.get('min_length_warning', {}).get('ko', ''),
                    required=q.get('required', True),
                    na_option_en=q.get('na_option', {}).get('en', ''),
                    na_option_ko=q.get('na_option', {}).get('ko', ''),
                    embedded_data=q.get('embedded_data', False),
                    conditional_display=q.get('conditional_display', {}) or {},
                    content_en=q.get('content', {}).get('en', ''),
                    content_ko=q.get('content', {}).get('ko', ''),
                )
                for opt in q.get('options', []):
                    SurveyOption.objects.create(
                        question=question,
                        order=opt['order'],
                        label_en=opt['label']['en'],
                        label_ko=opt['label'].get('ko', ''),
                        value=opt['value'],
                    )
        action = 'created' if created else 'updated'
        self.stdout.write(f'  {action}: {slug}')

    @staticmethod
    def _validate_unique_slugs(questions: list[dict], *, context: str) -> None:
        """Reject duplicate non-empty slugs within a single survey.

        Empty slugs are common on display_only blocks (no need to reference)
        and are exempt from uniqueness — DB constraint matches.
        """
        seen: dict[str, int] = {}
        for idx, q in enumerate(questions):
            slug = q.get('slug', '') or ''
            if not slug:
                continue
            if slug in seen:
                raise CommandError(
                    f'Duplicate question slug {slug!r} in {context} '
                    f'(positions {seen[slug]} and {idx})'
                )
            seen[slug] = idx


def _load_yaml_with_anchor_lookup(text: str) -> dict:
    """Parse YAML and return both the parsed data AND a lookup of `&name → value`.

    PyYAML's Composer populates `loader.anchors` (name → Node) during
    compose_document but resets it to `{}` at the end of that method, so we
    can't read it after the fact. The subclass below captures the dict into
    a side-channel attribute (`_captured_anchor_nodes`) right before the
    reset happens. We then construct the captured nodes' Python values.
    """

    class _AnchorCapturingLoader(yaml.SafeLoader):
        _captured_anchor_nodes: dict[str, yaml.Node] = {}

        def compose_document(self_inner):  # noqa: N805 — yaml.Composer protocol
            self_inner.get_event()  # DOCUMENT-START
            node = self_inner.compose_node(None, None)
            self_inner.get_event()  # DOCUMENT-END
            # Snapshot anchors BEFORE PyYAML's superclass would reset them.
            self_inner._captured_anchor_nodes = dict(self_inner.anchors)
            self_inner.anchors = {}
            return node

    loader = _AnchorCapturingLoader(text)
    try:
        root = loader.get_single_node()
        # construct_object caches by node identity, so the same object that
        # ends up in `data` is the one returned here — aliases keep ref
        # identity through the result graph.
        anchors: dict[str, object] = {
            name: loader.construct_object(node, deep=True)
            for name, node in loader._captured_anchor_nodes.items()
        }
        data = loader.construct_object(root, deep=True) if root is not None else None
    finally:
        loader.dispose()
    return {'data': data, 'anchors': anchors}


def _expand_includes(items: list, anchors: dict, *, context: str) -> list:
    """Walk a list of question dicts and splice each `_include: name` directive
    with the named anchor's contents.

    Supports nested includes (an anchored block can itself contain `_include`
    entries). Cycle detection guards against `a → b → a` loops.
    """
    return _expand_includes_inner(items, anchors, seen=set(), context=context)


def _expand_includes_inner(items: list, anchors: dict, *, seen: set[str], context: str) -> list:
    out: list = []
    for entry in items:
        if isinstance(entry, dict) and INCLUDE_DIRECTIVE in entry and len(entry) == 1:
            name = entry[INCLUDE_DIRECTIVE]
            if name not in anchors:
                raise CommandError(
                    f'_include references unknown anchor {name!r} in {context}'
                )
            if name in seen:
                raise CommandError(
                    f'_include cycle detected at {name!r} in {context}'
                )
            target = anchors[name]
            if not isinstance(target, list):
                raise CommandError(
                    f'_include {name!r} must reference a list anchor in {context}, '
                    f'got {type(target).__name__}'
                )
            out.extend(_expand_includes_inner(target, anchors, seen=seen | {name}, context=context))
        else:
            out.append(entry)
    return out
