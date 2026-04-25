from django.core.management.base import BaseCommand, CommandError

from chat.wit_admin import (
    ensure_wit_admin_user,
    ensure_blast_rooms,
    provision_user_rooms,
    regular_recipients,
    resolve_operators,
)


class Command(BaseCommand):
    help = (
        "Idempotently provision the WIT Admin user, the 3 operator blast rooms, "
        "and per-user (1 WIT Admin chat + 3 proxy rooms) for every regular user."
    )

    def handle(self, *args, **options):
        ensure_wit_admin_user()
        try:
            resolve_operators()
        except LookupError as e:
            raise CommandError(str(e)) from e

        ensure_blast_rooms()

        users = regular_recipients()
        total = users.count()
        for i, user in enumerate(users.iterator(chunk_size=500), 1):
            provision_user_rooms(user)
            if i % 100 == 0:
                self.stdout.write(f"  ... provisioned {i}/{total}")

        self.stdout.write(self.style.SUCCESS(
            f"Seeded WIT Admin chats for {total} users."
        ))
