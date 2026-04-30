from django.core.management.base import BaseCommand

from chat.wit_admin import ensure_system_connections, regular_recipients
from chat.wit_bot import ensure_wit_bot_room, ensure_wit_bot_user


class Command(BaseCommand):
    help = (
        "Idempotently create the wit_bot user and provision a wit_bot 1-on-1 "
        "ChatRoom for every regular user."
    )

    def handle(self, *args, **options):
        ensure_wit_bot_user()
        # ensure_system_connections is idempotent and now picks up wit_bot.
        ensure_system_connections()

        users = regular_recipients()
        total = users.count()
        for i, user in enumerate(users.iterator(chunk_size=500), 1):
            ensure_wit_bot_room(user)
            if i % 100 == 0:
                self.stdout.write(f"  ... provisioned {i}/{total}")

        self.stdout.write(self.style.SUCCESS(
            f"Seeded wit_bot rooms for {total} users."
        ))
