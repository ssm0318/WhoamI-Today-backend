"""Bootstrap WhoamI system accounts and provision their chat infrastructure.

Idempotent. Designed to run automatically after `migrate` (see start.sh) so a
fresh DB ends up with all 5 system accounts present, friended, and connected
to every regular user via the WIT-Admin / wit_bot rooms.

The 5 system accounts:
    wit_admin   — support inbox identity
    wit_bot     — system bot peer
    jaewon      — operator/replier (the only operator allowed to reply/blast)
    koyrkr      — operator/observer
    njs         — operator/observer

Newly-created system rows get is_superuser=True, is_staff=True, and a default
password (env: SYSTEM_USER_DEFAULT_PASSWORD, fallback 'Adoor2020:)' for dev).
Existing rows are left untouched — no flag upgrades, no password resets.
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from chat.wit_admin import (
    OPERATOR_OBSERVER_EMAILS,
    OPERATOR_REPLIER_EMAIL,
    WIT_ADMIN_EMAIL,
    WIT_ADMIN_USERNAME,
    ensure_blast_rooms,
    ensure_system_connections,
    ensure_wit_admin_user,
    provision_user_rooms,
    regular_recipients,
)
from chat.wit_bot import (
    WIT_BOT_EMAIL,
    WIT_BOT_USERNAME,
    ensure_wit_bot_room,
    ensure_wit_bot_user,
)


DEFAULT_PASSWORD = 'Adoor2020:)'


class Command(BaseCommand):
    help = (
        "Idempotently create the 5 WhoamI system accounts as superusers, "
        "friend them with each other, and provision WIT-Admin + wit_bot chat "
        "rooms for every regular user."
    )

    def handle(self, *args, **options):
        self._create_system_users()
        ensure_wit_admin_user()
        ensure_wit_bot_user()
        ensure_blast_rooms()
        ensure_system_connections()

        users = regular_recipients()
        total = users.count()
        for i, user in enumerate(users.iterator(chunk_size=500), 1):
            provision_user_rooms(user)
            ensure_wit_bot_room(user)
            if i % 100 == 0:
                self.stdout.write(f"  ... provisioned {i}/{total}")

        self.stdout.write(self.style.SUCCESS(
            f"Bootstrapped system users; provisioned chat rooms for {total} regular users."
        ))

    @transaction.atomic
    def _create_system_users(self):
        """Create any missing system rows as superusers. Skip rows that exist."""
        User = get_user_model()
        password = os.environ.get('SYSTEM_USER_DEFAULT_PASSWORD', DEFAULT_PASSWORD)

        # (username, email) — operators first, then bots. Bots don't have to be
        # superusers for the chat flow itself, but the user-stated requirement
        # is that all 5 are superusers.
        specs = [
            ('jaewon', OPERATOR_REPLIER_EMAIL),
            ('koyrkr', OPERATOR_OBSERVER_EMAILS[0]),
            ('njs', OPERATOR_OBSERVER_EMAILS[1]),
            (WIT_ADMIN_USERNAME, WIT_ADMIN_EMAIL),
            (WIT_BOT_USERNAME, WIT_BOT_EMAIL),
        ]

        for username, email in specs:
            if User.all_objects.filter(email=email).exists():
                self.stdout.write(f"  - {username}: row with email {email} already exists; leaving as-is.")
                continue
            if User.all_objects.filter(username=username).exists():
                self.stdout.write(f"  - {username}: row with username already exists; leaving as-is.")
                continue
            User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
            )
            self.stdout.write(f"  + Created superuser: {username} ({email})")
