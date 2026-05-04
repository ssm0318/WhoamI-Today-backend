"""Daily summary of wit_bot onboarding progress, emailed to operators.

Usage:
    python manage.py wit_bot_daily_summary
    python manage.py wit_bot_daily_summary --dry-run        # print to stdout, no email
    python manage.py wit_bot_daily_summary --to a@b.com,c@d.com  # override recipients
    python manage.py wit_bot_daily_summary --stale-hours 24      # threshold for "behind"

Send weekday-mornings via cron during the study window.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from chat.models import OnboardingScreenshot, WitBotConversationState
from chat.wit_admin import ALL_OPERATOR_EMAILS, WIT_ADMIN_EMAIL


User = get_user_model()


class Command(BaseCommand):
    help = "Email operators a daily summary of wit_bot onboarding progress."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print the email to stdout instead of sending.',
        )
        parser.add_argument(
            '--to', type=str, default=None,
            help='Comma-separated recipient list (overrides ALL_OPERATOR_EMAILS).',
        )
        parser.add_argument(
            '--stale-hours', type=int, default=24,
            help='Hours after which an in-progress kickoff or pending screenshot '
                 'counts as "behind".',
        )

    def handle(self, *args, **options):
        report = build_report(stale_hours=options['stale_hours'])
        text = render_report(report)

        if options['dry_run']:
            self.stdout.write(self.style.MIGRATE_HEADING('--- dry-run ---'))
            self.stdout.write(text)
            return

        recipients = (
            [r.strip() for r in options['to'].split(',') if r.strip()]
            if options['to']
            else list(ALL_OPERATOR_EMAILS)
        )
        if not recipients:
            self.stderr.write('No recipients; nothing to send.')
            return

        subject = f"WITty daily summary — {timezone.now().date()}"
        send_mail(
            subject=subject,
            message=text,
            from_email=None,  # uses DEFAULT_FROM_EMAIL
            recipient_list=recipients,
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS(
            f'Sent summary to {len(recipients)} recipient(s).'
        ))


def build_report(stale_hours: int = 24) -> dict:
    """Compute aggregate + per-user stats for the summary."""
    now = timezone.now()
    stale_cutoff = now - timedelta(hours=stale_hours)

    # Exclude operators + bots from participant pool
    excluded_emails = list(ALL_OPERATOR_EMAILS) + [WIT_ADMIN_EMAIL]
    participants_qs = User.objects.exclude(email__in=excluded_emails).exclude(
        username__in=('wit_bot', 'wit_admin'),
    ).exclude(is_superuser=True)

    total = participants_qs.count()

    started = 0
    kickoff_complete = 0
    audit_zero_missing = 0
    boss_passed = 0
    behind_kickoff = []

    for u in participants_qs:
        state = WitBotConversationState.objects.filter(user=u).first()
        if not state:
            continue
        ver = u.current_ver
        prog = state.context.get(ver, {}) if state.context else {}
        kickoff = prog.get('kickoff', {})
        if kickoff:
            started += 1
        if kickoff.get('completed'):
            kickoff_complete += 1
        else:
            # Started but not complete — check staleness
            if kickoff and state.updated_at and state.updated_at < stale_cutoff:
                behind_kickoff.append({
                    'username': u.username,
                    'version': ver,
                    'last_intent': state.current_intent,
                    'updated_at': state.updated_at.isoformat(),
                })
        audit = prog.get('audit', {})
        if audit.get('last_missing_count') == 0:
            audit_zero_missing += 1
        final = prog.get('final_quiz', {})
        if final.get('passed'):
            boss_passed += 1

    pending_shots = OnboardingScreenshot.objects.filter(status='pending').select_related('user')
    stale_pending_shots = pending_shots.filter(created_at__lt=stale_cutoff)

    return {
        'generated_at': now.isoformat(),
        'stale_hours': stale_hours,
        'totals': {
            'participants': total,
            'kickoff_started': started,
            'kickoff_complete': kickoff_complete,
            'audit_zero_missing': audit_zero_missing,
            'boss_passed': boss_passed,
        },
        'pending_screenshots': {
            'total': pending_shots.count(),
            'stale': [
                {
                    'username': shot.user.username,
                    'kind': shot.kind,
                    'version': shot.version,
                    'created_at': shot.created_at.isoformat(),
                }
                for shot in stale_pending_shots
            ],
        },
        'behind_kickoff': behind_kickoff,
    }


def render_report(report: dict) -> str:
    """Format the report dict as plain text for email."""
    t = report['totals']
    lines = [
        f"WITty daily summary — generated at {report['generated_at']}",
        f"Stale threshold: {report['stale_hours']}h",
        '',
        '── Totals ──────────────────────────────',
        f"  Participants:               {t['participants']}",
        f"  Kickoff started:            {t['kickoff_started']}",
        f"  Kickoff complete:           {t['kickoff_complete']}",
        f"  Audit at 0 missing:         {t['audit_zero_missing']}",
        f"  Boss quiz passed:           {t['boss_passed']}",
        '',
    ]

    pending = report['pending_screenshots']
    lines.append(f"── Pending screenshots: {pending['total']} ──")
    if pending['stale']:
        lines.append(f"  Stale (>{report['stale_hours']}h):")
        for shot in pending['stale']:
            lines.append(
                f"    • {shot['username']} ({shot['version']}) — {shot['kind']}, "
                f"submitted {shot['created_at']}"
            )
    else:
        lines.append("  No stale pending screenshots.")
    lines.append('')

    behind = report['behind_kickoff']
    lines.append(f"── Behind on kickoff: {len(behind)} ──")
    if behind:
        for entry in behind:
            lines.append(
                f"    • {entry['username']} ({entry['version']}) — "
                f"intent={entry['last_intent']!r}, "
                f"last touched {entry['updated_at']}"
            )
    else:
        lines.append("  Everyone in-progress is current.")
    lines.append('')

    lines.append("Review pending screenshots: /api/secret/chat/onboardingscreenshot/?status=pending")
    return '\n'.join(lines)
