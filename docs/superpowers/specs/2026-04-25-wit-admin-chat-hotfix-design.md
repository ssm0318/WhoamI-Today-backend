# WIT Admin Chat Hotfix — Design

**Date:** 2026-04-25
**Branch:** `feat/wit-admin-chat-hotfix` (off `release/final-research`)
**Scope:** Backend-only hotfix. No frontend changes.

## Goal

Give every regular user a 1:1 chat with a virtual "WIT Admin" support persona. Three operator accounts (`koyrkr@gmail.com`, `njs03332@gmail.com`, `jaewonkim628@gmail.com`) observe inbound messages. Only `jaewonkim628@gmail.com` ("jaewon") replies, and his replies appear to the user as if from "WIT Admin". Jaewon can also broadcast a single message to every user as WIT Admin, with the broadcast also visible to the other two operators.

## Personas

- **Regular user (User A):** sees one chat with "WIT Admin". Sends messages and receives replies/broadcasts. Has no idea three humans observe behind the scenes.
- **Jaewon:** the only operator who replies. Has per-user observer chats (one per user) where he sees inbound messages and types replies. Has a separate composer chat with WIT Admin where he types broadcasts.
- **Koyrkr, Njs:** read-only observers. Have per-user observer chats and a single broadcast log chat. They are not blocked from typing, but their messages are intentionally not propagated.
- **WIT Admin:** a real Django `User` row used as the visible counterparty for regular users. Never logs in; it's a backend identity.

## Architecture

### New persistent state

**`ChatRoom`** gains two boolean flags (default `False`):

- `is_wit_admin_proxy` — marks per-user observer rooms: `User ↔ koyrkr`, `User ↔ njs03332`, `User ↔ jaewon`. Used by the signal to identify "this is jaewon's reply lane" or "this is an observer mirror, don't fan out further".
- `is_wit_admin_blast_room` — marks each operator's personal room with WIT Admin: `jaewon ↔ WIT_Admin` (composer + history), `koyrkr ↔ WIT_Admin` (read-only log), `njs03332 ↔ WIT_Admin` (read-only log).

**`Message`** gains one boolean flag (default `False`):

- `is_wit_admin_mirror` — set on every message created by the fan-out signal. Functions as the recursion guard.

### Per-account room layout

After seeding (and after signup, via auto-signal):

| Account | Rooms |
|---|---|
| Regular user A | 1 chat: `A ↔ WIT_Admin` |
| Jaewon | N proxy chats (one per user) + 1 `jaewon ↔ WIT_Admin` blast room |
| Koyrkr | N proxy chats + 1 `koyrkr ↔ WIT_Admin` blast log |
| Njs03332 | N proxy chats + 1 `njs03332 ↔ WIT_Admin` blast log |
| WIT Admin | N user chats + 3 operator blast rooms |

### Fan-out signal — single `post_save(Message)` handler

```text
on_message_created(message):
    if message.is_wit_admin_mirror:
        return                              # loop guard

    room = message.chat_room
    sender = message.sender
    branch_1: room is `<user> ↔ WIT_Admin` and sender != WIT_Admin
        → for admin in [koyrkr, njs, jaewon]:
            mirror_room = ChatRoom(is_wit_admin_proxy=True) for (user, admin)
            create Message(
                chat_room=mirror_room,
                sender=user, receiver=admin,
                content=message.content,
                is_wit_admin_mirror=True,
            )

    branch_2: room.is_wit_admin_proxy and sender == jaewon
        → user = the non-jaewon participant of room
        → wit_room = ChatRoom for (user, WIT_Admin)
        → create Message(
            chat_room=wit_room,
            sender=WIT_Admin, receiver=user,
            content=message.content,
            is_wit_admin_mirror=True,
        )

    branch_3: room.is_wit_admin_blast_room and sender == jaewon
        → recipients = active, non-deleted users excluding
                       WIT_Admin and the three operators
        → for user in recipients:
            wit_room = ChatRoom for (user, WIT_Admin)
            create Message(
                chat_room=wit_room,
                sender=WIT_Admin, receiver=user,
                content=message.content,
                is_wit_admin_mirror=True,
            )
        → for observer in [koyrkr, njs]:
            log_room = observer's blast log room
            create Message(
                chat_room=log_room,
                sender=WIT_Admin, receiver=observer,
                content=message.content,
                is_wit_admin_mirror=True,
            )

    else: no-op  (covers koyrkr/njs typing in any of their rooms)
```

Branch ordering is mutually exclusive by room flag, so a single `if/elif/elif` is fine.

### Why this can't loop

Every mirrored message has `is_wit_admin_mirror=True` and the handler returns immediately on that flag. The original message in the user-facing or jaewon-facing room has `is_wit_admin_mirror=False` and triggers exactly one fan-out pass.

### Message types mirrored

Mirror copies the meaningful payload fields: `content`, `image`, `message_type`/`emoji` if present. Reactions, edits, replies, and read state are NOT propagated across mirrors (out of scope; YAGNI). Each room maintains its own unread state.

## Seed management command

`python manage.py seed_wit_admin_chats`

1. Idempotently create the WIT Admin user: `username='wit_admin'`, email `whoami.today.official@gmail.com`, display name "WIT Admin", `is_active=False` so it can never log in, password set via `set_unusable_password()`.
2. Resolve the three operator users by email; abort with a clear error if any is missing.
3. Idempotently create the three operator blast rooms (`is_wit_admin_blast_room=True`).
4. For every active, non-deleted regular user (excluding WIT Admin and the three operators):
   - Get-or-create `User ↔ WIT_Admin` (no flag).
   - For each operator, get-or-create the per-user observer room with `is_wit_admin_proxy=True`.
5. Log counts: users processed, rooms created, rooms already present.

Re-running the command is safe: rooms are looked up by participants, flags re-asserted on existing rows.

## Auto-create on signup

`post_save` signal on `User` (registered in `account/signals.py` and wired through `account/apps.py`):
- Skip if the new user is WIT Admin or one of the three operators.
- Skip if `is_active=False` or soft-deleted.
- Run the same per-user creation step as the seed (1 `User ↔ WIT_Admin` chat + 3 `is_wit_admin_proxy=True` rooms).
- Wrapped in `@transaction.atomic` per the project's signal convention.

This keeps the system self-healing for new signups without re-running the management command.

## Pinning the WIT Admin chat

The chat list view (`chat/views.py:ChatRoomList.get_queryset`) currently orders by `-last_message_time`. To pin the WIT Admin chat (and, for operator accounts, their blast room with WIT Admin) at the top:

- Add an annotation `is_pinned_top` that is `True` when either room participant is the WIT Admin user.
- Order by `-is_pinned_top, -last_message_time`.
- This pins the room even before any message exists in it, *but* the existing `.filter(last_message_time__isnull=False)` would hide an empty room. Drop that filter for pinned rooms specifically — i.e. allow the WIT Admin chat to appear without messages, while non-pinned rooms keep the existing "must have messages" filter.

Effect by account:
- Regular user A: `A ↔ WIT_Admin` is always at the top of their chat list.
- Operator (jaewon/koyrkr/njs): their `*_↔ WIT_Admin` blast room is at the top; per-user proxy chats sort below normally.
- WIT Admin: never logs in; no UI concern.

The pin is implicit (driven by participant identity), not a user-controlled flag — so no per-user pin state to migrate. Verify during implementation whether the WebSocket-driven chat list (`ChatListConsumer`) reuses this queryset or builds its own ordering; if separate, mirror the change.

## Files touched

Backend only:

- `adoorback/chat/models.py` — add the two `ChatRoom` flags and one `Message` flag.
- `adoorback/chat/migrations/` — three migrations per the project's 3-step migration safety pattern (`MIGRATION_GUIDELINES.md`). See "Migration plan" below.
- `adoorback/chat/views.py` — extend `ChatRoomList.get_queryset` to annotate `is_pinned_top` and reorder.
- `adoorback/chat/signals.py` — new file (or extend existing) with the `post_save` handler. Register in `adoorback/chat/apps.py` `ready()`.
- `adoorback/chat/management/commands/seed_wit_admin_chats.py` — new command.
- `adoorback/account/signals.py` (or wherever the `User` post_save lives) — auto-create rooms on signup.
- `adoorback/chat/tests.py` (or new test module) — coverage as listed below.

Frontend: none. WIT Admin appears as a normal 1:1 counterparty; mirror chats appear as normal 1:1 chats in operator accounts.

## Migration plan

Per `MIGRATION_GUIDELINES.md`, every new column is added in three migrations:

**Step 1 — Add nullable columns:**
- `ChatRoom.is_wit_admin_proxy = BooleanField(null=True, blank=True, default=False)`
- `ChatRoom.is_wit_admin_blast_room = BooleanField(null=True, blank=True, default=False)`
- `Message.is_wit_admin_mirror = BooleanField(null=True, blank=True, default=False)`

**Step 2 — `RunPython` backfill:** set every existing row's three flags to `False`. Reverse function sets them back to `None` (no-op semantically since they all start `False`). Verify counts before/after.

**Step 3 — Apply NOT NULL constraint:** `AlterField` to `BooleanField(default=False)` (no longer nullable).

Each step is its own migration file. `python manage.py sqlmigrate chat <num>` should be inspected before applying.

## Edge cases

- **Soft-deleted / inactive users:** excluded from seed loops and the signup signal.
- **WIT Admin and the 3 operators:** excluded from the regular-user fan-out loop. They don't get a `User ↔ WIT_Admin` chat; operators have their dedicated blast rooms instead.
- **ChatRequest gating:** the project may require an accepted `ChatRequest` for 1:1 messaging. If so, the seed pre-creates the request in `accepted` state for every room it creates; the auto-signup signal does the same. To verify in code before implementation.
- **Friendship gating:** if 1:1 chat APIs reject non-friends at the serializer/view layer, the backend message creation in the signal handler must bypass the API layer and write directly via the ORM (already the case since the handler uses `Message.objects.create`).
- **WebSocket delivery:** existing consumers should pick up programmatically-created `Message` rows. To verify by triggering a fan-out and watching the user's WS stream during implementation.
- **Group rooms:** all six flag-bearing rooms are 1:1 (`is_group=False`). Flags on group rooms are nonsensical and never set.

## Testing

Django `TestCase` with these scenarios:

1. **Seed idempotency** — running `seed_wit_admin_chats` twice produces no duplicates; counts match expected values.
2. **Inbound fan-out** — `User A → WIT_Admin` produces exactly 3 mirror messages (one per operator), each flagged `is_wit_admin_mirror=True`, with sender=user, receiver=admin.
3. **Jaewon reply fan-in** — message in `User A ↔ jaewon` proxy room with sender=jaewon produces 1 mirror in `User A ↔ WIT_Admin` with sender=WIT_Admin.
4. **Koyrkr/Njs reply** — message in their proxy rooms with sender=koyrkr or njs produces NO mirrors. Original message is not deleted.
5. **Blast** — message in `jaewon ↔ WIT_Admin` produces N mirror messages (one per regular user, sender=WIT_Admin) plus 2 mirrors in koyrkr's and njs's blast logs.
6. **Loop guard** — mirror messages do not retrigger the handler (assert handler call count or final message count).
7. **Auto-signup** — creating a new `User` produces 1 + 3 rooms automatically; soft-deleted/inactive users do not.
8. **Pin** — `ChatRoomList` returns the WIT Admin chat first regardless of `last_message_time` (including when empty), and operator accounts get their blast room first.

## Out of scope (YAGNI)

- Reaction/edit/delete propagation across mirrors.
- Read-receipt sync between original and mirror rooms.
- Blocking koyrkr/njs from typing in their proxy or blast rooms.
- Frontend customization of the WIT Admin avatar/badge (uses default User rendering).
- An admin-side "view all blasts" dashboard.
- Per-message routing rules, throttling, or rate-limiting on blasts.

## Verification gates before merge

- `python manage.py check` clean.
- `python manage.py makemigrations --check` clean.
- All new tests pass.
- Manual smoke test in dev: seed runs, send a message as a regular user, observe mirrors land in operator accounts; reply as jaewon, observe message arrives at user from WIT Admin; send a blast, observe N user deliveries plus 2 observer log entries.
- Frontend `npx craco build` passes (no changes expected, but sanity-check).
- Dev-server preview shows no console errors.
