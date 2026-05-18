import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from surveys.models import ScheduledSurvey
from surveys.sidebar_order import (
    apply_sidebar_order_to_model,
    normalize_sidebar_order_map,
    write_sidebar_order_source,
)


class Command(BaseCommand):
    help = (
        'Apply explicit ScheduledSurvey.sidebar_order values from a JSON map. '
        'Use --write-source to persist the same map in surveys/sidebar_order.py '
        'so future setup_survey_state runs keep the committed order.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--json',
            dest='json_map',
            help='JSON object keyed by "<cadence>:<sequence_index>" with integer order values.',
        )
        parser.add_argument(
            '--file',
            dest='json_file',
            help='Path to a JSON file containing the order map.',
        )
        parser.add_argument(
            '--clear-missing',
            action='store_true',
            help='Clear sidebar_order on rows omitted from the supplied map.',
        )
        parser.add_argument(
            '--write-source',
            action='store_true',
            help='Rewrite surveys/sidebar_order.py with the supplied non-null order map.',
        )

    def handle(self, *args, **opts):
        if opts['json_map'] and opts['json_file']:
            raise CommandError('Pass only one of --json or --file.')

        if opts['json_file']:
            raw_text = Path(opts['json_file']).read_text(encoding='utf-8')
        elif opts['json_map']:
            raw_text = opts['json_map']
        else:
            raw_text = '{}'

        try:
            raw_map = json.loads(raw_text)
            order_map = normalize_sidebar_order_map(raw_map)
        except (json.JSONDecodeError, ValueError) as exc:
            raise CommandError(str(exc))

        result = apply_sidebar_order_to_model(
            ScheduledSurvey,
            order_map,
            clear_missing=opts['clear_missing'],
        )

        source_path = None
        if opts['write_source']:
            source_path = write_sidebar_order_source(order_map)

        self.stdout.write(
            self.style.SUCCESS(
                'Applied survey sidebar order: '
                f'updated={len(result["updated"])} '
                f'cleared={len(result["cleared"])} '
                f'missing={len(result["missing"])}'
            )
        )
        if result['missing']:
            self.stdout.write('Missing schedule rows: ' + ', '.join(result['missing']))
        if source_path:
            self.stdout.write(f'Wrote source map: {source_path}')
