from pathlib import Path

import yaml
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from surveys.models import Survey, SurveyOption, SurveyQuestion


class Command(BaseCommand):
    help = (
        'Load survey definitions from a YAML/JSON fixture. '
        'Idempotent on slug: existing surveys are updated; new ones are created.'
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
            data = yaml.safe_load(text)
        elif path.suffix == '.json':
            import json
            data = json.loads(text)
        else:
            raise CommandError(f'Unsupported extension: {path.suffix}')
        if not isinstance(data, list):
            raise CommandError('Top-level fixture must be a list of surveys.')
        with transaction.atomic():
            for entry in data:
                self._upsert(entry, replace_questions=opts['replace_questions'])
        self.stdout.write(self.style.SUCCESS(f'Loaded {len(data)} surveys from {path}'))

    def _upsert(self, entry, *, replace_questions: bool):
        slug = entry['slug']
        # Survey-level `type` becomes the default for all questions in the survey;
        # individual questions can override via their own `type` field.
        default_type = entry.get('type', SurveyQuestion._meta.get_field('type').default)
        defaults = {
            'title_en': entry['title']['en'],
            'title_ko': entry['title']['ko'],
            'description_en': entry.get('description', {}).get('en', ''),
            'description_ko': entry.get('description', {}).get('ko', ''),
            'interpretation_en': entry.get('interpretation', {}).get('en', ''),
            'interpretation_ko': entry.get('interpretation', {}).get('ko', ''),
            'friend_visible': entry.get('friend_visible', True),
            'results_hidden': entry.get('results_hidden', False),
        }
        survey, created = Survey.objects.update_or_create(slug=slug, defaults=defaults)
        if replace_questions or created:
            survey.questions.all().delete()
            for q in entry.get('questions', []):
                question = SurveyQuestion.objects.create(
                    survey=survey,
                    order=q['order'],
                    type=q.get('type', default_type),
                    prompt_en=q['prompt']['en'],
                    prompt_ko=q['prompt']['ko'],
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
                )
                for opt in q.get('options', []):
                    SurveyOption.objects.create(
                        question=question,
                        order=opt['order'],
                        label_en=opt['label']['en'],
                        label_ko=opt['label']['ko'],
                        value=opt['value'],
                    )
        action = 'created' if created else 'updated'
        self.stdout.write(f'  {action}: {slug}')
