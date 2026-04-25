# WIT Admin Chat Hotfix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every regular user a 1:1 chat with a virtual "WIT Admin"; fan inbound messages out to three operator observers; let `jaewonkim628@gmail.com` reply (appearing as WIT Admin) or broadcast to all users.

**Architecture:** Two new `ChatRoom` flags (`is_wit_admin_proxy`, `is_wit_admin_blast_room`) plus one `Message` flag (`is_wit_admin_mirror`) drive a single `post_save(Message)` handler with three branches (inbound, jaewon-reply, jaewon-blast). A management command + a `post_save(User)` signal idempotently provision the rooms. `ChatRoomList.get_queryset` pins WIT Admin rooms to the top.

**Tech Stack:** Django 4.2, DRF, PostgreSQL, Django Channels (existing infra), `safedelete`.

**Branch:** `feat/wit-admin-chat-hotfix` (off `release/final-research`). All commits on this branch.

**Spec reference:** `docs/superpowers/specs/2026-04-25-wit-admin-chat-hotfix-design.md`

---

## File Map

| File | Status | Responsibility |
|---|---|---|
| `adoorback/chat/models.py` | modify | Add 3 new boolean fields; add new `post_save(Message)` branches |
| `adoorback/chat/migrations/0010_wit_admin_flags_nullable.py` | create | Step 1 — add nullable flags |
| `adoorback/chat/migrations/0011_wit_admin_flags_backfill.py` | create | Step 2 — RunPython backfill False |
| `adoorback/chat/migrations/0012_wit_admin_flags_notnull.py` | create | Step 3 — AlterField NOT NULL |
| `adoorback/chat/wit_admin.py` | create | Constants, lookup helpers, recipient query, room-provisioning helper |
| `adoorback/chat/management/__init__.py` | create | Marker |
| `adoorback/chat/management/commands/__init__.py` | create | Marker |
| `adoorback/chat/management/commands/seed_wit_admin_chats.py` | create | Idempotent seed command |
| `adoorback/chat/views.py` | modify | Pin WIT Admin chats in `ChatRoomList` |
| `adoorback/account/models.py` | modify | Add `post_save(User)` to provision rooms on signup |
| `adoorback/chat/tests_wit_admin.py` | create | All new test coverage |

Three migration files keep the schema change auditable per `MIGRATION_GUIDELINES.md`. The `wit_admin.py` helper module isolates business logic from `models.py`. Signals live in `models.py` to match the existing project convention (the file already hosts `create_message_notification` and `create_chat_request_noti`).

---

## Operator email constants

These three values are referenced repeatedly. Defined once in `chat/wit_admin.py`:

```python
WIT_ADMIN_USERNAME = 'wit_admin'
WIT_ADMIN_EMAIL = 'whoami.today.official@gmail.com'
WIT_ADMIN_DISPLAY_NAME = 'WIT Admin'

OPERATOR_REPLIER_EMAIL = 'jaewonkim628@gmail.com'   # only one allowed to reply / blast
OPERATOR_OBSERVER_EMAILS = ('koyrkr@gmail.com', 'njs03332@gmail.com')
ALL_OPERATOR_EMAILS = (OPERATOR_REPLIER_EMAIL,) + OPERATOR_OBSERVER_EMAILS
```

---

## Task 1 — Step-1 migration: add nullable flag fields

**Files:**
- Modify: `adoorback/chat/models.py` (lines around 30, 90 — add fields)
- Create: `adoorback/chat/migrations/0010_wit_admin_flags_nullable.py`
- Test: `adoorback/chat/tests_wit_admin.py`

- [ ] **Step 1: Write the failing test**

Create `adoorback/chat/tests_wit_admin.py` with:

```python
from django.contrib.auth import get_user_model
from django.test import TestCase

from chat.models import ChatRoom, Message

User = get_user_model()


class WitAdminFieldsTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username='alice', email='alice@example.com', password='x')
        self.bob = User.objects.create_user(username='bob', email='bob@example.com', password='x')

    def test_chatroom_has_wit_admin_proxy_flag(self):
        room = ChatRoom.objects.create(user1=self.alice, user2=self.bob)
        self.assertFalse(room.is_wit_admin_proxy)

    def test_chatroom_has_blast_room_flag(self):
        room = ChatRoom.objects.create(user1=self.alice, user2=self.bob)
        self.assertFalse(room.is_wit_admin_blast_room)

    def test_message_has_mirror_flag(self):
        room = ChatRoom.objects.create(user1=self.alice, user2=self.bob)
        msg = Message.objects.create(chat_room=room, sender=self.alice, receiver=self.bob, content='hi')
        self.assertFalse(msg.is_wit_admin_mirror)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source ~/.nvm/nvm.sh && nvm use 18  # not needed but harmless
cd adoorback
DB_HOST=localhost python manage.py test chat.tests_wit_admin -v 2
```

Expected: errors mentioning unknown field `is_wit_admin_proxy`.

- [ ] **Step 3: Add the model fields (nullable)**

In `adoorback/chat/models.py`, inside `class ChatRoom` after `members = ...`:

```python
    # WIT Admin hotfix — see docs/superpowers/specs/2026-04-25-wit-admin-chat-hotfix-design.md
    is_wit_admin_proxy = models.BooleanField(null=True, blank=True, default=False)
    is_wit_admin_blast_room = models.BooleanField(null=True, blank=True, default=False)
```

In `class Message` after `is_read = ...`:

```python
    # WIT Admin hotfix loop guard
    is_wit_admin_mirror = models.BooleanField(null=True, blank=True, default=False)
```

- [ ] **Step 4: Generate migration 0010**

```bash
cd adoorback
DB_HOST=localhost python manage.py makemigrations chat --name wit_admin_flags_nullable
```

Expected: creates `chat/migrations/0010_wit_admin_flags_nullable.py` with three `AddField` operations.

- [ ] **Step 5: Inspect generated SQL**

```bash
DB_HOST=localhost python manage.py sqlmigrate chat 0010
```

Expected: three `ALTER TABLE ... ADD COLUMN ... NULL` statements with `DEFAULT FALSE`. No data manipulation.

- [ ] **Step 6: Apply migration and run tests**

```bash
DB_HOST=localhost python manage.py migrate chat
DB_HOST=localhost python manage.py test chat.tests_wit_admin -v 2
```

Expected: 3 tests pass.

- [ ] **Step 7: Commit**

```bash
cd /Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-backend
git add adoorback/chat/models.py adoorback/chat/migrations/0010_wit_admin_flags_nullable.py adoorback/chat/tests_wit_admin.py
git commit -m "feat(chat): add nullable WIT Admin flags (step 1/3)"
```

---

## Task 2 — Step-2 migration: backfill existing rows

**Files:**
- Create: `adoorback/chat/migrations/0011_wit_admin_flags_backfill.py`
- Test: `adoorback/chat/tests_wit_admin.py`

- [ ] **Step 1: Write the failing test**

Append to `tests_wit_admin.py`:

```python
class WitAdminFlagsBackfillTests(TestCase):
    """Smoke check: after the backfill migration runs, every row must have False (not NULL)."""

    def test_all_chatrooms_have_non_null_flags(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        u1 = User.objects.create_user(username='u1', email='u1@example.com', password='x')
        u2 = User.objects.create_user(username='u2', email='u2@example.com', password='x')
        ChatRoom.objects.create(user1=u1, user2=u2)
        for room in ChatRoom.objects.all():
            self.assertIsNotNone(room.is_wit_admin_proxy)
            self.assertIsNotNone(room.is_wit_admin_blast_room)
```

This test passes after step-1 (default=False) — it acts as a regression guard for step-2/3.

- [ ] **Step 2: Run test to verify it passes**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin -v 2
```

Expected: all tests pass (we're really proving the regression guard works).

- [ ] **Step 3: Create the backfill migration**

Create `adoorback/chat/migrations/0011_wit_admin_flags_backfill.py`:

```python
from django.db import migrations


def backfill_flags(apps, schema_editor):
    ChatRoom = apps.get_model('chat', 'ChatRoom')
    Message = apps.get_model('chat', 'Message')
    ChatRoom.objects.filter(is_wit_admin_proxy__isnull=True).update(is_wit_admin_proxy=False)
    ChatRoom.objects.filter(is_wit_admin_blast_room__isnull=True).update(is_wit_admin_blast_room=False)
    Message.objects.filter(is_wit_admin_mirror__isnull=True).update(is_wit_admin_mirror=False)


def reverse_noop(apps, schema_editor):
    # Reverse is a no-op: setting back to NULL would be allowed at this stage but
    # has no semantic value. Idempotent for safety.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0010_wit_admin_flags_nullable'),
    ]

    operations = [
        migrations.RunPython(backfill_flags, reverse_noop),
    ]
```

- [ ] **Step 4: Inspect SQL plan**

```bash
DB_HOST=localhost python manage.py sqlmigrate chat 0011
```

Expected: a `RunPython` notice (no raw SQL printed since it's Python).

- [ ] **Step 5: Apply migration and run tests**

```bash
DB_HOST=localhost python manage.py migrate chat
DB_HOST=localhost python manage.py test chat.tests_wit_admin -v 2
```

Expected: 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add adoorback/chat/migrations/0011_wit_admin_flags_backfill.py adoorback/chat/tests_wit_admin.py
git commit -m "feat(chat): backfill WIT Admin flags on existing rows (step 2/3)"
```

---

## Task 3 — Step-3 migration: tighten to NOT NULL

**Files:**
- Modify: `adoorback/chat/models.py` (drop `null=True, blank=True` from the three new fields)
- Create: `adoorback/chat/migrations/0012_wit_admin_flags_notnull.py`

- [ ] **Step 1: Write the failing test**

Append to `tests_wit_admin.py`:

```python
class WitAdminFlagsNotNullTests(TestCase):
    def test_proxy_field_rejects_null(self):
        from django.db import IntegrityError
        from django.contrib.auth import get_user_model
        User = get_user_model()
        u1 = User.objects.create_user(username='nx1', email='nx1@example.com', password='x')
        u2 = User.objects.create_user(username='nx2', email='nx2@example.com', password='x')
        room = ChatRoom.objects.create(user1=u1, user2=u2)
        # Attempting to NULL the column directly via raw SQL must fail post-step-3.
        from django.db import connection
        with connection.cursor() as cur:
            with self.assertRaises(IntegrityError):
                cur.execute(
                    "UPDATE chat_chatroom SET is_wit_admin_proxy = NULL WHERE id = %s",
                    [room.id],
                )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin.WitAdminFlagsNotNullTests -v 2
```

Expected: the raw SQL UPDATE succeeds (NULL is currently allowed) — test fails.

- [ ] **Step 3: Update model field declarations to NOT NULL**

In `adoorback/chat/models.py`, change the three new field lines to:

```python
    is_wit_admin_proxy = models.BooleanField(default=False)
    is_wit_admin_blast_room = models.BooleanField(default=False)
```

```python
    is_wit_admin_mirror = models.BooleanField(default=False)
```

- [ ] **Step 4: Generate migration 0012**

```bash
DB_HOST=localhost python manage.py makemigrations chat --name wit_admin_flags_notnull
```

Expected: three `AlterField` operations, each going from `null=True` to `null=False`.

- [ ] **Step 5: Inspect SQL**

```bash
DB_HOST=localhost python manage.py sqlmigrate chat 0012
```

Expected: `ALTER TABLE ... ALTER COLUMN ... SET NOT NULL` for each of the three fields.

- [ ] **Step 6: Apply migration and run tests**

```bash
DB_HOST=localhost python manage.py migrate chat
DB_HOST=localhost python manage.py test chat.tests_wit_admin -v 2
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add adoorback/chat/models.py adoorback/chat/migrations/0012_wit_admin_flags_notnull.py adoorback/chat/tests_wit_admin.py
git commit -m "feat(chat): enforce NOT NULL on WIT Admin flags (step 3/3)"
```

---

## Task 4 — Helper module: `chat/wit_admin.py`

**Files:**
- Create: `adoorback/chat/wit_admin.py`
- Test: `adoorback/chat/tests_wit_admin.py`

- [ ] **Step 1: Write the failing test**

Append to `tests_wit_admin.py`:

```python
class WitAdminHelpersTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        # Operators
        self.jaewon = User.objects.create_user(
            username='jaewon', email='jaewonkim628@gmail.com', password='x',
        )
        self.koyrkr = User.objects.create_user(
            username='koyrkr', email='koyrkr@gmail.com', password='x',
        )
        self.njs = User.objects.create_user(
            username='njs', email='njs03332@gmail.com', password='x',
        )
        # Regular users
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        self.bob = User.objects.create_user(username='b', email='b@e.com', password='x')

    def test_ensure_wit_admin_user_creates_inactive(self):
        from chat.wit_admin import ensure_wit_admin_user
        wit = ensure_wit_admin_user()
        self.assertEqual(wit.username, 'wit_admin')
        self.assertEqual(wit.email, 'whoami.today.official@gmail.com')
        self.assertFalse(wit.is_active)
        self.assertFalse(wit.has_usable_password())

    def test_ensure_wit_admin_user_idempotent(self):
        from chat.wit_admin import ensure_wit_admin_user
        a = ensure_wit_admin_user()
        b = ensure_wit_admin_user()
        self.assertEqual(a.id, b.id)

    def test_resolve_operators_returns_three(self):
        from chat.wit_admin import resolve_operators
        ops = resolve_operators()
        self.assertEqual({u.email for u in ops}, {
            'jaewonkim628@gmail.com', 'koyrkr@gmail.com', 'njs03332@gmail.com',
        })

    def test_resolve_operators_raises_on_missing(self):
        from django.contrib.auth import get_user_model
        from chat.wit_admin import resolve_operators
        User = get_user_model()
        User.objects.filter(email='koyrkr@gmail.com').delete()
        with self.assertRaises(LookupError):
            resolve_operators()

    def test_provision_user_rooms_creates_four(self):
        from chat.wit_admin import provision_user_rooms, ensure_wit_admin_user
        ensure_wit_admin_user()
        from chat.models import ChatRoom
        provision_user_rooms(self.alice)
        # 1 wit_admin chat + 3 proxy rooms = 4
        wit_rooms = ChatRoom.objects.filter(
            Q(user1=self.alice) | Q(user2=self.alice)
        )
        self.assertEqual(wit_rooms.count(), 4)
        self.assertEqual(wit_rooms.filter(is_wit_admin_proxy=True).count(), 3)

    def test_provision_user_rooms_idempotent(self):
        from chat.wit_admin import provision_user_rooms, ensure_wit_admin_user
        ensure_wit_admin_user()
        from chat.models import ChatRoom
        provision_user_rooms(self.alice)
        provision_user_rooms(self.alice)
        wit_rooms = ChatRoom.objects.filter(Q(user1=self.alice) | Q(user2=self.alice))
        self.assertEqual(wit_rooms.count(), 4)

    def test_ensure_blast_rooms_creates_three(self):
        from chat.wit_admin import ensure_blast_rooms, ensure_wit_admin_user
        ensure_wit_admin_user()
        from chat.models import ChatRoom
        ensure_blast_rooms()
        self.assertEqual(ChatRoom.objects.filter(is_wit_admin_blast_room=True).count(), 3)

    def test_regular_recipients_excludes_operators_and_inactive(self):
        from chat.wit_admin import regular_recipients, ensure_wit_admin_user
        ensure_wit_admin_user()
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_user(username='dead', email='d@e.com', password='x', is_active=False)
        emails = {u.email for u in regular_recipients()}
        self.assertIn('a@e.com', emails)
        self.assertIn('b@e.com', emails)
        self.assertNotIn('jaewonkim628@gmail.com', emails)
        self.assertNotIn('koyrkr@gmail.com', emails)
        self.assertNotIn('njs03332@gmail.com', emails)
        self.assertNotIn('whoami.today.official@gmail.com', emails)
        self.assertNotIn('d@e.com', emails)
```

Add `from django.db.models import Q` to the imports at the top of the file.

- [ ] **Step 2: Run test to verify it fails**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin.WitAdminHelpersTests -v 2
```

Expected: `ModuleNotFoundError: No module named 'chat.wit_admin'`.

- [ ] **Step 3: Implement helpers**

Create `adoorback/chat/wit_admin.py`:

```python
"""Helpers for the WIT Admin chat hotfix.

See docs/superpowers/specs/2026-04-25-wit-admin-chat-hotfix-design.md.
"""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from chat.models import ChatRoom


WIT_ADMIN_USERNAME = 'wit_admin'
WIT_ADMIN_EMAIL = 'whoami.today.official@gmail.com'
WIT_ADMIN_DISPLAY_NAME = 'WIT Admin'

OPERATOR_REPLIER_EMAIL = 'jaewonkim628@gmail.com'
OPERATOR_OBSERVER_EMAILS = ('koyrkr@gmail.com', 'njs03332@gmail.com')
ALL_OPERATOR_EMAILS = (OPERATOR_REPLIER_EMAIL,) + OPERATOR_OBSERVER_EMAILS


def ensure_wit_admin_user():
    """Get-or-create the WIT Admin user. Idempotent."""
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=WIT_ADMIN_USERNAME,
        defaults={
            'email': WIT_ADMIN_EMAIL,
            'is_active': False,
        },
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=['password'])
    # Reassert critical attributes if the row pre-existed with drift
    changed = False
    if user.email != WIT_ADMIN_EMAIL:
        user.email = WIT_ADMIN_EMAIL
        changed = True
    if user.is_active:
        user.is_active = False
        changed = True
    if changed:
        user.save(update_fields=['email', 'is_active'])
    return user


def resolve_operators():
    """Return [jaewon, koyrkr, njs] as User objects. Raise LookupError if any missing."""
    User = get_user_model()
    operators = []
    for email in ALL_OPERATOR_EMAILS:
        u = User.objects.filter(email=email).first()
        if u is None:
            raise LookupError(f"Operator user with email {email!r} not found")
        operators.append(u)
    return operators


def get_replier():
    """Return the jaewon operator user (the only one allowed to reply/blast)."""
    User = get_user_model()
    user = User.objects.filter(email=OPERATOR_REPLIER_EMAIL).first()
    if user is None:
        raise LookupError(f"Replier user {OPERATOR_REPLIER_EMAIL!r} not found")
    return user


def _ordered_pair(a, b):
    """Match ChatRoom.save() ordering convention (user1.id < user2.id)."""
    return (a, b) if a.id < b.id else (b, a)


@transaction.atomic
def provision_user_rooms(user):
    """Create the 1 WIT-Admin chat + 3 operator proxy rooms for `user`. Idempotent."""
    wit = ensure_wit_admin_user()
    operators = resolve_operators()

    # Skip if `user` is WIT Admin or an operator
    if user.id == wit.id or user.email in ALL_OPERATOR_EMAILS:
        return

    u1, u2 = _ordered_pair(user, wit)
    ChatRoom.objects.get_or_create(user1=u1, user2=u2)

    for op in operators:
        u1, u2 = _ordered_pair(user, op)
        room, _ = ChatRoom.objects.get_or_create(user1=u1, user2=u2)
        if not room.is_wit_admin_proxy:
            room.is_wit_admin_proxy = True
            room.save(update_fields=['is_wit_admin_proxy'])


@transaction.atomic
def ensure_blast_rooms():
    """Create the 3 operator-↔-WIT-Admin blast rooms. Idempotent."""
    wit = ensure_wit_admin_user()
    for op in resolve_operators():
        u1, u2 = _ordered_pair(wit, op)
        room, _ = ChatRoom.objects.get_or_create(user1=u1, user2=u2)
        if not room.is_wit_admin_blast_room:
            room.is_wit_admin_blast_room = True
            room.save(update_fields=['is_wit_admin_blast_room'])


def regular_recipients():
    """Active, non-deleted users excluding WIT Admin and the 3 operators."""
    User = get_user_model()
    excluded = list(ALL_OPERATOR_EMAILS) + [WIT_ADMIN_EMAIL]
    return User.objects.filter(is_active=True).exclude(email__in=excluded)


def is_wit_admin(user):
    return user is not None and user.username == WIT_ADMIN_USERNAME


def is_replier(user):
    return user is not None and user.email == OPERATOR_REPLIER_EMAIL
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin.WitAdminHelpersTests -v 2
```

Expected: 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add adoorback/chat/wit_admin.py adoorback/chat/tests_wit_admin.py
git commit -m "feat(chat): add WIT Admin helper module"
```

---

## Task 5 — Seed management command

**Files:**
- Create: `adoorback/chat/management/__init__.py` (empty)
- Create: `adoorback/chat/management/commands/__init__.py` (empty)
- Create: `adoorback/chat/management/commands/seed_wit_admin_chats.py`
- Test: `adoorback/chat/tests_wit_admin.py`

- [ ] **Step 1: Write the failing test**

Append to `tests_wit_admin.py`:

```python
class SeedWitAdminChatsCommandTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.jaewon = User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        self.koyrkr = User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        self.njs = User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        self.bob = User.objects.create_user(username='bob', email='b@e.com', password='x')

    def test_command_creates_expected_rooms(self):
        from django.core.management import call_command
        call_command('seed_wit_admin_chats')
        # 2 regular users * (1 wit_admin + 3 proxy) = 8, plus 3 blast rooms = 11
        self.assertEqual(ChatRoom.objects.count(), 11)
        self.assertEqual(ChatRoom.objects.filter(is_wit_admin_proxy=True).count(), 6)
        self.assertEqual(ChatRoom.objects.filter(is_wit_admin_blast_room=True).count(), 3)

    def test_command_is_idempotent(self):
        from django.core.management import call_command
        call_command('seed_wit_admin_chats')
        first = ChatRoom.objects.count()
        call_command('seed_wit_admin_chats')
        self.assertEqual(ChatRoom.objects.count(), first)

    def test_command_aborts_when_operator_missing(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        self.koyrkr.delete()
        with self.assertRaises(CommandError):
            call_command('seed_wit_admin_chats')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin.SeedWitAdminChatsCommandTests -v 2
```

Expected: `Unknown command: 'seed_wit_admin_chats'`.

- [ ] **Step 3: Create empty `__init__.py` files**

```bash
mkdir -p adoorback/chat/management/commands
touch adoorback/chat/management/__init__.py
touch adoorback/chat/management/commands/__init__.py
```

- [ ] **Step 4: Implement the command**

Create `adoorback/chat/management/commands/seed_wit_admin_chats.py`:

```python
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
            raise CommandError(str(e))

        ensure_blast_rooms()

        users = regular_recipients()
        total = users.count()
        for i, user in enumerate(users, 1):
            provision_user_rooms(user)
            if i % 100 == 0:
                self.stdout.write(f"  ... provisioned {i}/{total}")

        self.stdout.write(self.style.SUCCESS(
            f"Seeded WIT Admin chats for {total} users."
        ))
```

- [ ] **Step 5: Run tests**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin.SeedWitAdminChatsCommandTests -v 2
```

Expected: 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add adoorback/chat/management/__init__.py adoorback/chat/management/commands/__init__.py adoorback/chat/management/commands/seed_wit_admin_chats.py adoorback/chat/tests_wit_admin.py
git commit -m "feat(chat): add seed_wit_admin_chats management command"
```

---

## Task 6 — Auto-signup signal

**Files:**
- Modify: `adoorback/account/models.py` (append a new `post_save(User)` receiver)
- Test: `adoorback/chat/tests_wit_admin.py`

- [ ] **Step 1: Write the failing test**

Append to `tests_wit_admin.py`:

```python
class AutoSignupProvisioningTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        # Pre-create operators so resolve_operators() succeeds
        User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        from chat.wit_admin import ensure_wit_admin_user, ensure_blast_rooms
        ensure_wit_admin_user()
        ensure_blast_rooms()

    def test_new_user_gets_four_rooms_automatically(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        new_user = User.objects.create_user(username='new', email='new@e.com', password='x')
        rooms = ChatRoom.objects.filter(Q(user1=new_user) | Q(user2=new_user))
        self.assertEqual(rooms.count(), 4)
        self.assertEqual(rooms.filter(is_wit_admin_proxy=True).count(), 3)

    def test_inactive_new_user_skipped(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        new_user = User.objects.create_user(
            username='nope', email='nope@e.com', password='x', is_active=False,
        )
        rooms = ChatRoom.objects.filter(Q(user1=new_user) | Q(user2=new_user))
        self.assertEqual(rooms.count(), 0)

    def test_operator_signup_does_not_get_provisioned(self):
        # Already pre-created in setUp; check no per-operator user-rooms exist
        # for jaewon as a regular user (he should only be in proxy + blast rooms).
        from django.contrib.auth import get_user_model
        User = get_user_model()
        jaewon = User.objects.get(email='jaewonkim628@gmail.com')
        # No room where jaewon is the "regular user" with WIT Admin (i.e., his is the
        # blast room, not a regular-user provision)
        from chat.wit_admin import ensure_wit_admin_user
        wit = ensure_wit_admin_user()
        u1, u2 = (jaewon, wit) if jaewon.id < wit.id else (wit, jaewon)
        rooms = ChatRoom.objects.filter(user1=u1, user2=u2)
        # Exactly one room — the blast room — must be flagged as such.
        self.assertEqual(rooms.count(), 1)
        self.assertTrue(rooms.first().is_wit_admin_blast_room)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin.AutoSignupProvisioningTests -v 2
```

Expected: `test_new_user_gets_four_rooms_automatically` fails with `0 != 4`.

- [ ] **Step 3: Add the signal receiver**

In `adoorback/account/models.py`, append at the end of the file (after the existing `delete_old_profile_image` receiver):

```python
@transaction.atomic
@receiver(post_save, sender=User)
def provision_wit_admin_rooms(created, instance, **kwargs):
    """On user signup, create the WIT Admin chat + 3 operator proxy rooms.

    See docs/superpowers/specs/2026-04-25-wit-admin-chat-hotfix-design.md.
    """
    if not created:
        return
    if instance.deleted:
        return
    if not instance.is_active:
        return

    # Lazy import to avoid circular: chat.wit_admin imports chat.models which can
    # transitively reach account.models.
    from chat.wit_admin import provision_user_rooms, ALL_OPERATOR_EMAILS, WIT_ADMIN_EMAIL

    if instance.email in ALL_OPERATOR_EMAILS or instance.email == WIT_ADMIN_EMAIL:
        return

    try:
        provision_user_rooms(instance)
    except LookupError:
        # Operator users not yet seeded — silently skip; the management command
        # will catch this user up on the next run.
        return
```

- [ ] **Step 4: Run tests**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin.AutoSignupProvisioningTests -v 2
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add adoorback/account/models.py adoorback/chat/tests_wit_admin.py
git commit -m "feat(account): auto-provision WIT Admin rooms on signup"
```

---

## Task 7 — Inbound fan-out signal (user → 3 operators)

**Files:**
- Modify: `adoorback/chat/models.py` — add new branches to a new `post_save(Message)` handler (separate from `create_message_notification`)
- Test: `adoorback/chat/tests_wit_admin.py`

- [ ] **Step 1: Write the failing test**

Append to `tests_wit_admin.py`:

```python
class InboundFanOutTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.core.management import call_command
        User = get_user_model()
        self.jaewon = User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        self.koyrkr = User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        self.njs = User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        call_command('seed_wit_admin_chats')

    def _wit_admin(self):
        from chat.wit_admin import ensure_wit_admin_user
        return ensure_wit_admin_user()

    def _alice_wit_room(self):
        wit = self._wit_admin()
        u1, u2 = (self.alice, wit) if self.alice.id < wit.id else (wit, self.alice)
        return ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=False)

    def test_user_message_fans_out_to_three_proxy_rooms(self):
        room = self._alice_wit_room()
        msg = Message.objects.create(
            chat_room=room, sender=self.alice, receiver=self._wit_admin(), content='hello',
        )
        # Original counts as 1; expect 3 mirrors in the 3 proxy rooms
        mirrors = Message.objects.filter(is_wit_admin_mirror=True)
        self.assertEqual(mirrors.count(), 3)
        self.assertEqual({m.receiver.email for m in mirrors}, {
            'jaewonkim628@gmail.com', 'koyrkr@gmail.com', 'njs03332@gmail.com',
        })
        for m in mirrors:
            self.assertEqual(m.sender, self.alice)
            self.assertEqual(m.content, 'hello')
            self.assertTrue(m.chat_room.is_wit_admin_proxy)

    def test_wit_admin_sender_does_not_fanout_inbound(self):
        room = self._alice_wit_room()
        wit = self._wit_admin()
        Message.objects.create(chat_room=room, sender=wit, receiver=self.alice, content='from-admin')
        # No inbound mirrors for outbound message direction
        self.assertEqual(Message.objects.filter(is_wit_admin_mirror=True, sender=wit).count(), 0)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin.InboundFanOutTests -v 2
```

Expected: `0 != 3` — no fan-out yet.

- [ ] **Step 3: Add a helper for copying message payload**

In `adoorback/chat/wit_admin.py`, append:

```python
def _copy_message_fields(source):
    """Return kwargs for Message.objects.create() that mirror `source`'s payload."""
    return {
        'content': source.content,
        'emoji': source.emoji,
        'image': source.image,
        'shared_content_type': source.shared_content_type,
        'shared_object_id': source.shared_object_id,
        'is_wit_admin_mirror': True,
    }
```

- [ ] **Step 4: Add the new `post_save(Message)` receiver**

In `adoorback/chat/models.py`, append at the end of the file:

```python
@transaction.atomic
@receiver(post_save, sender=Message)
def fanout_wit_admin_messages(created, instance, **kwargs):
    """WIT Admin hotfix fan-out / fan-in / blast handler.

    Branches:
      1. Inbound user → WIT Admin     → mirror to 3 operator proxy rooms.
      2. Jaewon reply → user proxy    → mirror to user's WIT Admin room as WIT Admin.
      3. Jaewon blast → blast room    → fan out to all users + 2 observer logs.

    See docs/superpowers/specs/2026-04-25-wit-admin-chat-hotfix-design.md.
    """
    if not created:
        return
    if instance.is_wit_admin_mirror:
        return  # loop guard

    # Lazy import to avoid circular module load
    from chat.wit_admin import (
        ensure_wit_admin_user, resolve_operators, _copy_message_fields,
        is_wit_admin, is_replier,
    )

    room = instance.chat_room
    sender = instance.sender

    # Branch 1 — inbound user → WIT Admin
    is_user_to_wit_admin_room = (
        not room.is_group
        and not room.is_wit_admin_proxy
        and not room.is_wit_admin_blast_room
        and (is_wit_admin(room.user1) or is_wit_admin(room.user2))
        and not is_wit_admin(sender)
    )
    if is_user_to_wit_admin_room:
        try:
            operators = resolve_operators()
        except LookupError:
            return
        user = sender  # the regular user
        for op in operators:
            u1, u2 = (user, op) if user.id < op.id else (op, user)
            proxy_room = ChatRoom.objects.filter(
                user1=u1, user2=u2, is_wit_admin_proxy=True,
            ).first()
            if proxy_room is None:
                # Auto-heal: provision then re-fetch
                from chat.wit_admin import provision_user_rooms
                provision_user_rooms(user)
                proxy_room = ChatRoom.objects.get(
                    user1=u1, user2=u2, is_wit_admin_proxy=True,
                )
            Message.objects.create(
                chat_room=proxy_room,
                sender=user,
                receiver=op,
                **_copy_message_fields(instance),
            )
```

- [ ] **Step 5: Run tests**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin.InboundFanOutTests -v 2
```

Expected: 2 tests pass.

- [ ] **Step 6: Commit**

```bash
git add adoorback/chat/models.py adoorback/chat/wit_admin.py adoorback/chat/tests_wit_admin.py
git commit -m "feat(chat): fan inbound user→WIT-Admin messages to 3 operator proxy rooms"
```

---

## Task 8 — Jaewon reply fan-in signal

**Files:**
- Modify: `adoorback/chat/models.py` — extend `fanout_wit_admin_messages` with branch 2
- Test: `adoorback/chat/tests_wit_admin.py`

- [ ] **Step 1: Write the failing test**

Append to `tests_wit_admin.py`:

```python
class JaewonReplyFanInTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.core.management import call_command
        User = get_user_model()
        self.jaewon = User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        self.koyrkr = User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        self.njs = User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        call_command('seed_wit_admin_chats')

    def _wit(self):
        from chat.wit_admin import ensure_wit_admin_user
        return ensure_wit_admin_user()

    def _alice_jaewon_proxy(self):
        u1, u2 = (self.alice, self.jaewon) if self.alice.id < self.jaewon.id else (self.jaewon, self.alice)
        return ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=True)

    def _alice_wit_room(self):
        wit = self._wit()
        u1, u2 = (self.alice, wit) if self.alice.id < wit.id else (wit, self.alice)
        return ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=False)

    def test_jaewon_reply_in_proxy_mirrors_to_user_wit_room(self):
        proxy = self._alice_jaewon_proxy()
        Message.objects.create(
            chat_room=proxy, sender=self.jaewon, receiver=self.alice, content='reply',
        )
        wit_room = self._alice_wit_room()
        mirrors = Message.objects.filter(
            chat_room=wit_room, is_wit_admin_mirror=True, sender=self._wit(),
        )
        self.assertEqual(mirrors.count(), 1)
        self.assertEqual(mirrors.first().content, 'reply')
        self.assertEqual(mirrors.first().receiver, self.alice)

    def test_koyrkr_reply_does_not_fanin(self):
        u1, u2 = (self.alice, self.koyrkr) if self.alice.id < self.koyrkr.id else (self.koyrkr, self.alice)
        proxy = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=True)
        Message.objects.create(chat_room=proxy, sender=self.koyrkr, receiver=self.alice, content='nope')
        # No mirror should appear in the WIT Admin room
        wit_room = self._alice_wit_room()
        self.assertEqual(Message.objects.filter(chat_room=wit_room).count(), 0)

    def test_njs_reply_does_not_fanin(self):
        u1, u2 = (self.alice, self.njs) if self.alice.id < self.njs.id else (self.njs, self.alice)
        proxy = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=True)
        Message.objects.create(chat_room=proxy, sender=self.njs, receiver=self.alice, content='nope')
        wit_room = self._alice_wit_room()
        self.assertEqual(Message.objects.filter(chat_room=wit_room).count(), 0)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin.JaewonReplyFanInTests -v 2
```

Expected: `test_jaewon_reply_in_proxy_mirrors_to_user_wit_room` fails (`0 != 1`).

- [ ] **Step 3: Add branch 2 to the receiver**

In `adoorback/chat/models.py`, inside `fanout_wit_admin_messages`, after branch 1 add:

```python
    # Branch 2 — jaewon reply in proxy room → mirror to user's WIT Admin room
    if room.is_wit_admin_proxy and is_replier(sender):
        # Identify the regular user as the non-jaewon participant
        user = room.user2 if room.user1_id == sender.id else room.user1
        wit = ensure_wit_admin_user()
        u1, u2 = (user, wit) if user.id < wit.id else (wit, user)
        wit_room = ChatRoom.objects.filter(
            user1=u1, user2=u2, is_wit_admin_proxy=False,
        ).first()
        if wit_room is None:
            from chat.wit_admin import provision_user_rooms
            provision_user_rooms(user)
            wit_room = ChatRoom.objects.get(
                user1=u1, user2=u2, is_wit_admin_proxy=False,
            )
        Message.objects.create(
            chat_room=wit_room,
            sender=wit,
            receiver=user,
            **_copy_message_fields(instance),
        )
        return
```

- [ ] **Step 4: Run tests**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin.JaewonReplyFanInTests -v 2
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add adoorback/chat/models.py adoorback/chat/tests_wit_admin.py
git commit -m "feat(chat): mirror Jaewon proxy replies back as WIT Admin"
```

---

## Task 9 — Jaewon blast fan-out

**Files:**
- Modify: `adoorback/chat/models.py` — branch 3
- Test: `adoorback/chat/tests_wit_admin.py`

- [ ] **Step 1: Write the failing test**

Append to `tests_wit_admin.py`:

```python
class JaewonBlastTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.core.management import call_command
        User = get_user_model()
        self.jaewon = User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        self.koyrkr = User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        self.njs = User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        self.bob = User.objects.create_user(username='bob', email='b@e.com', password='x')
        call_command('seed_wit_admin_chats')

    def _wit(self):
        from chat.wit_admin import ensure_wit_admin_user
        return ensure_wit_admin_user()

    def _jaewon_blast_room(self):
        wit = self._wit()
        u1, u2 = (self.jaewon, wit) if self.jaewon.id < wit.id else (wit, self.jaewon)
        return ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_blast_room=True)

    def test_jaewon_blast_reaches_all_users(self):
        blast = self._jaewon_blast_room()
        Message.objects.create(
            chat_room=blast, sender=self.jaewon, receiver=self._wit(),
            content='announcement',
        )
        # Mirror to alice's and bob's WIT Admin rooms (sender=wit)
        wit = self._wit()
        for user in (self.alice, self.bob):
            u1, u2 = (user, wit) if user.id < wit.id else (wit, user)
            wit_room = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=False)
            user_msgs = Message.objects.filter(
                chat_room=wit_room, is_wit_admin_mirror=True, sender=wit,
            )
            self.assertEqual(user_msgs.count(), 1, f"Missing blast for {user.username}")
            self.assertEqual(user_msgs.first().content, 'announcement')

    def test_jaewon_blast_mirrors_into_observer_logs(self):
        blast = self._jaewon_blast_room()
        Message.objects.create(
            chat_room=blast, sender=self.jaewon, receiver=self._wit(),
            content='announcement',
        )
        wit = self._wit()
        for op in (self.koyrkr, self.njs):
            u1, u2 = (wit, op) if wit.id < op.id else (op, wit)
            log = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_blast_room=True)
            mirrors = Message.objects.filter(
                chat_room=log, is_wit_admin_mirror=True, sender=wit,
            )
            self.assertEqual(mirrors.count(), 1, f"Missing log entry for {op.username}")

    def test_koyrkr_typing_in_own_blast_log_does_nothing(self):
        wit = self._wit()
        u1, u2 = (wit, self.koyrkr) if wit.id < self.koyrkr.id else (self.koyrkr, wit)
        log = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_blast_room=True)
        Message.objects.create(chat_room=log, sender=self.koyrkr, receiver=wit, content='leak')
        # No fan-out: no messages anywhere except the original in koyrkr's log
        self.assertEqual(Message.objects.exclude(chat_room=log).count(), 0)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin.JaewonBlastTests -v 2
```

Expected: `test_jaewon_blast_reaches_all_users` fails.

- [ ] **Step 3: Add branch 3 to the receiver**

In `adoorback/chat/models.py`, inside `fanout_wit_admin_messages`, after branch 2 add:

```python
    # Branch 3 — jaewon blast in his blast room → fan out to all users + 2 observer logs
    if room.is_wit_admin_blast_room and is_replier(sender):
        from chat.wit_admin import (
            regular_recipients, OPERATOR_OBSERVER_EMAILS,
        )
        wit = ensure_wit_admin_user()

        # 3a — every regular user's WIT Admin room
        for user in regular_recipients():
            u1, u2 = (user, wit) if user.id < wit.id else (wit, user)
            wit_room = ChatRoom.objects.filter(
                user1=u1, user2=u2, is_wit_admin_proxy=False,
            ).first()
            if wit_room is None:
                from chat.wit_admin import provision_user_rooms
                provision_user_rooms(user)
                wit_room = ChatRoom.objects.get(
                    user1=u1, user2=u2, is_wit_admin_proxy=False,
                )
            Message.objects.create(
                chat_room=wit_room,
                sender=wit,
                receiver=user,
                **_copy_message_fields(instance),
            )

        # 3b — observer (koyrkr, njs) blast logs
        from django.contrib.auth import get_user_model
        User = get_user_model()
        for email in OPERATOR_OBSERVER_EMAILS:
            observer = User.objects.filter(email=email).first()
            if observer is None:
                continue
            u1, u2 = (wit, observer) if wit.id < observer.id else (observer, wit)
            log_room = ChatRoom.objects.filter(
                user1=u1, user2=u2, is_wit_admin_blast_room=True,
            ).first()
            if log_room is None:
                continue
            Message.objects.create(
                chat_room=log_room,
                sender=wit,
                receiver=observer,
                **_copy_message_fields(instance),
            )
        return
```

- [ ] **Step 4: Run tests**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin.JaewonBlastTests -v 2
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add adoorback/chat/models.py adoorback/chat/tests_wit_admin.py
git commit -m "feat(chat): broadcast Jaewon blast as WIT Admin to all users + observer logs"
```

---

## Task 10 — Loop-guard regression test

**Files:**
- Test only: `adoorback/chat/tests_wit_admin.py`

- [ ] **Step 1: Write the regression test**

Append to `tests_wit_admin.py`:

```python
class LoopGuardTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.core.management import call_command
        User = get_user_model()
        User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        call_command('seed_wit_admin_chats')

    def test_inbound_produces_exactly_three_mirrors_no_recursion(self):
        from chat.wit_admin import ensure_wit_admin_user
        wit = ensure_wit_admin_user()
        u1, u2 = (self.alice, wit) if self.alice.id < wit.id else (wit, self.alice)
        room = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=False)
        Message.objects.create(chat_room=room, sender=self.alice, receiver=wit, content='no-loop')
        # Total messages = 1 original + 3 mirrors = 4. Anything more = infinite loop.
        self.assertEqual(Message.objects.count(), 4)
        self.assertEqual(Message.objects.filter(is_wit_admin_mirror=True).count(), 3)

    def test_blast_produces_n_plus_two_no_recursion(self):
        from chat.wit_admin import ensure_wit_admin_user
        from django.contrib.auth import get_user_model
        wit = ensure_wit_admin_user()
        User = get_user_model()
        jaewon = User.objects.get(email='jaewonkim628@gmail.com')
        u1, u2 = (jaewon, wit) if jaewon.id < wit.id else (wit, jaewon)
        blast = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_blast_room=True)
        Message.objects.create(chat_room=blast, sender=jaewon, receiver=wit, content='broadcast')
        # 1 original + 1 (alice WIT room) + 2 (observer logs) = 4
        self.assertEqual(Message.objects.count(), 4)
        self.assertEqual(Message.objects.filter(is_wit_admin_mirror=True).count(), 3)
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin.LoopGuardTests -v 2
```

Expected: 2 tests pass.

- [ ] **Step 3: Commit**

```bash
git add adoorback/chat/tests_wit_admin.py
git commit -m "test(chat): regression-guard WIT Admin signal recursion"
```

---

## Task 11 — Pin WIT Admin chat in `ChatRoomList`

**Files:**
- Modify: `adoorback/chat/views.py` — extend `ChatRoomList.get_queryset`
- Test: `adoorback/chat/tests_wit_admin.py`

- [ ] **Step 1: Write the failing test**

Append to `tests_wit_admin.py`:

```python
class ChatListPinTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.core.management import call_command
        User = get_user_model()
        User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        self.charlie = User.objects.create_user(username='charlie', email='c@e.com', password='x')
        call_command('seed_wit_admin_chats')

    def _list(self, user):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from chat.views import ChatRoomList
        factory = APIRequestFactory()
        req = factory.get('/api/chat/rooms/')
        force_authenticate(req, user=user)
        view = ChatRoomList.as_view()
        resp = view(req)
        return resp.data

    def test_wit_admin_room_appears_first_for_regular_user(self):
        # Make charlie send alice a message to ensure their non-WIT chat has a last_message_time
        from chat.models import ChatRoom, get_or_create_chat_room
        from chat.wit_admin import ensure_wit_admin_user
        room = get_or_create_chat_room(self.alice, self.charlie)
        Message.objects.create(chat_room=room, sender=self.charlie, receiver=self.alice, content='hi')
        data = self._list(self.alice)
        # First entry should involve WIT Admin
        results = data.get('results', data)  # paginated or not
        first = results[0]
        wit = ensure_wit_admin_user()
        # The room id must be alice's WIT Admin room
        u1, u2 = (self.alice, wit) if self.alice.id < wit.id else (wit, self.alice)
        wit_room = ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=False)
        self.assertEqual(first['id'], wit_room.id)

    def test_wit_admin_room_appears_even_when_empty(self):
        # Alice has not messaged WIT Admin, has no other chats
        data = self._list(self.alice)
        results = data.get('results', data)
        self.assertGreaterEqual(len(results), 1)
        # The WIT Admin room is in the result list despite having no messages
```

- [ ] **Step 2: Run test to verify it fails**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin.ChatListPinTests -v 2
```

Expected: failure — the empty WIT Admin room is excluded by `last_message_time__isnull=False`, and ordering doesn't pin it.

- [ ] **Step 3: Update `ChatRoomList.get_queryset`**

In `adoorback/chat/views.py`, replace the body of `ChatRoomList.get_queryset` (currently lines ~34–53) with:

```python
    def get_queryset(self):
        from django.db.models import Case, When, Value, BooleanField
        from chat.wit_admin import WIT_ADMIN_USERNAME

        user = self.request.user

        latest_msg = Message.objects.filter(
            chat_room=OuterRef('pk')
        ).order_by('-created_at')

        is_pinned_top = Case(
            When(
                Q(user1__username=WIT_ADMIN_USERNAME) | Q(user2__username=WIT_ADMIN_USERNAME),
                then=Value(True),
            ),
            default=Value(False),
            output_field=BooleanField(),
        )

        return ChatRoom.objects.filter(
            Q(user1=user) | Q(user2=user) | Q(members=user)
        ).distinct().annotate(
            last_message_time=Subquery(latest_msg.values('created_at')[:1]),
            last_message_content=Subquery(latest_msg.values('content')[:1]),
            last_message_emoji=Subquery(latest_msg.values('emoji')[:1]),
            unread_cnt=Count(
                'messages',
                filter=Q(messages__receiver=user, messages__is_read=False)
            ),
            is_pinned_top=is_pinned_top,
        ).filter(
            Q(last_message_time__isnull=False) | Q(is_pinned_top=True)
        ).order_by('-is_pinned_top', '-last_message_time')
```

- [ ] **Step 4: Run tests**

```bash
DB_HOST=localhost python manage.py test chat.tests_wit_admin.ChatListPinTests -v 2
```

Expected: 2 tests pass.

- [ ] **Step 5: Sanity-check existing chat tests still pass**

```bash
DB_HOST=localhost python manage.py test chat -v 2
```

Expected: all pre-existing chat tests still pass.

- [ ] **Step 6: Commit**

```bash
git add adoorback/chat/views.py adoorback/chat/tests_wit_admin.py
git commit -m "feat(chat): pin WIT Admin chat to top of ChatRoomList"
```

---

## Task 12 — Verification gates

**Files:** none (verification only).

- [ ] **Step 1: `manage.py check` clean**

```bash
cd adoorback
DB_HOST=localhost python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 2: Migrations clean**

```bash
DB_HOST=localhost python manage.py makemigrations --check
```

Expected: no missing migrations.

- [ ] **Step 3: Full chat test suite**

```bash
DB_HOST=localhost python manage.py test chat -v 2
```

Expected: every test passes; counts include the new `tests_wit_admin` classes.

- [ ] **Step 4: Account test suite (auto-signup signal lives there)**

```bash
DB_HOST=localhost python manage.py test account -v 2
```

Expected: every test passes.

- [ ] **Step 5: Manual smoke check (optional but recommended)**

Start the backend dev server with `DB_HOST=localhost`. With three test users matching the three operator emails plus a regular user A:

1. Run `python manage.py seed_wit_admin_chats` — confirm "Seeded WIT Admin chats for N users."
2. Log in as A; observe `WIT Admin` chat at the top of the chat list.
3. Send a message from A to WIT Admin.
4. Log in as koyrkr; confirm a `User A` chat appears with the message.
5. Log in as jaewon; reply in the proxy chat with A.
6. Log in as A again; confirm the reply arrived as a message from WIT Admin.
7. Log in as jaewon; in his `WIT Admin` blast room, type a broadcast.
8. Log in as A and a second regular user; confirm both received the broadcast.
9. Log in as koyrkr; confirm the broadcast appears in his `WIT Admin` log.

- [ ] **Step 6: Frontend sanity build (no expected changes, just a guard)**

```bash
cd /Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-frontend
source ~/.nvm/nvm.sh && nvm use 18
npx craco build
```

Expected: build succeeds; no TypeScript or ESLint errors.

- [ ] **Step 7: Final summary commit (if anything is left uncommitted)**

```bash
cd /Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-backend
git status
# if clean, no commit; otherwise:
# git add -A && git commit -m "chore(chat): final hotfix verification fixes"
```

---

## Out of scope (do not implement)

- Reaction / edit / delete propagation across mirror messages.
- Read-receipt or unread-count synchronization between original and mirror rooms.
- Frontend custom WIT Admin avatar / badge rendering.
- Blocking koyrkr or njs from typing in their proxy / log rooms.
- A web-admin UI to view all blasts.
- Throttling or rate-limiting of blasts.
