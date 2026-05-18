from pathlib import Path

from django.core.management.base import BaseCommand

from surveys.audit import build_survey_audit, render_audit_html


DEFAULT_OUTPUT = Path(__file__).resolve().parents[5] / 'survey_audit.html'


class Command(BaseCommand):
    help = (
        'Generate a standalone local HTML page for auditing survey fixture '
        'content, schedule dates, audiences, and question lists.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            default=str(DEFAULT_OUTPUT),
            help='Output HTML path. Defaults to survey_audit.html in the workspace root.',
        )

    def handle(self, *args, **options):
        output = Path(options['output']).expanduser()
        if not output.is_absolute():
            output = Path.cwd() / output
        output.parent.mkdir(parents=True, exist_ok=True)

        audit = build_survey_audit()
        output.write_text(render_audit_html(audit), encoding='utf-8')

        summary = audit['summary']
        self.stdout.write(self.style.SUCCESS(f'Wrote survey audit page: {output}'))
        self.stdout.write(
            'Surveys={survey_count} Questions={question_count} '
            'ScheduleRows={schedule_row_count} Warnings={warning_count}'.format(**summary)
        )
