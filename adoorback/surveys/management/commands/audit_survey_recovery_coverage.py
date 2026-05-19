from pathlib import Path

import yaml
from django.core.management.base import BaseCommand

from surveys.recovery import build_recovery_coverage, load_recovery_manifest


class Command(BaseCommand):
    help = (
        'Generate a survey recovery coverage report from the current DB. '
        'Run this on production to see which participants still need each '
        'canonical final-schema question.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--manifest',
            help='Path to recovery_question_map.yaml. Defaults to surveys/fixtures/recovery_question_map.yaml.',
        )
        parser.add_argument(
            '--out',
            help='Output YAML path. If omitted, writes the report to stdout.',
        )

    def handle(self, *args, **opts):
        manifest = load_recovery_manifest(opts.get('manifest'))
        report = build_recovery_coverage(manifest)
        rendered = yaml.safe_dump(report, sort_keys=False, allow_unicode=True)

        out = opts.get('out')
        if out:
            path = Path(out)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding='utf-8')
            self.stdout.write(self.style.SUCCESS(f'Wrote recovery coverage report to {path}'))
        else:
            self.stdout.write(rendered)
