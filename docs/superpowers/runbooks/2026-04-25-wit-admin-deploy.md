# WIT Admin Chat Hotfix — Deployment Runbook

**Date:** 2026-04-25
**Spec:** `docs/superpowers/specs/2026-04-25-wit-admin-chat-hotfix-design.md`
**Plan:** `docs/superpowers/plans/2026-04-25-wit-admin-chat-hotfix.md`
**Branch:** `feat/wit-admin-chat-hotfix` (off `release/final-research`)

This runbook walks through the **one-time operational setup** required to enable the WIT Admin chat support channel on a live environment (staging or production). The hotfix's code (signals, helpers, seed command) ships with the branch; this document covers the **non-code steps** — user creation, passwords, data migration, and profile images.

> **Why a runbook and not more code?** Passwords, real user emails, and human-in-the-loop verifications shouldn't live in git. Each command below is run once per environment by an authorised admin.

---

## Pre-flight

Before starting:

- [ ] Code merged into the deployed branch and rolled out (CI applied migrations `chat/0010_*`, `chat/0011_*`, `chat/0012_*`).
- [ ] Backend `python manage.py check` is clean on the running container.
- [ ] You can run a Django shell on the target environment (`python manage.py shell` or `kubectl exec`, depending on your deploy).
- [ ] Backup the database (or have point-in-time recovery available) before step 5 — it touches every `qna_question` row.

---

## Step 1 — Operator users sign up via the frontend

The three operators sign in to the live app **as themselves**, using your normal signup flow, with their real email addresses. They each pick their own password. **You never see or commit these passwords.**

Required emails (must match exactly — the helper resolves operators by email):

| Role | Email |
|---|---|
| Replier (only one allowed to reply / blast) | `jaewonkim628@gmail.com` |
| Observer | `koyrkr@gmail.com` |
| Observer | `njs03332@gmail.com` |

After this step:
```bash
python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> U = get_user_model()
>>> for email in ['jaewonkim628@gmail.com', 'koyrkr@gmail.com', 'njs03332@gmail.com']:
...     u = U.objects.filter(email=email).first()
...     print(email, '->', u and u.username, 'active=' if u else '', u and u.is_active)
```
All three should resolve.

If any operator hasn't signed up yet, **stop here**. The seed in step 2 will abort cleanly with a `CommandError` listing the missing email.

---

## Step 2 — Run the seed command

```bash
python manage.py seed_wit_admin_chats
```

What this does (idempotent — safe to re-run any time):

1. Creates the `wit_admin` user with `username='wit_admin'`, `email='zeoni.res@gmail.com'`. **No password is set, so login is impossible until step 3.**
2. Creates 3 operator blast rooms (one per operator, each flagged `is_wit_admin_blast_room=True`).
3. For every active, non-deleted, non-operator, non-WIT-Admin user in the DB:
   - Creates a `User ↔ WIT_Admin` chat (no flag).
   - Creates 3 `User ↔ <operator>` proxy rooms (each flagged `is_wit_admin_proxy=True`).

Expected output:
```
Seeded WIT Admin chats for <N> users.
```
where `<N>` is the count of regular users at run time.

After this step, every new user signup will auto-provision their 4 rooms via the `provision_wit_admin_rooms` `post_save(User)` signal — no need to re-run the command for them.

---

## Step 3 — Set `wit_admin`'s password

`wit_admin` is the support persona that operators sign in to when they want to view the inbox the way a regular user would see it. It does NOT have admin/staff privileges; it's a regular login-able account.

```bash
python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> u = get_user_model().objects.get(username='wit_admin')
>>> u.set_password('<a strong password you generate>')   # NEVER commit this
>>> u.save()
>>> u.has_usable_password()  # → True
True
```

Share the password with operators **out-of-band** (1Password, Slack DM, Bitwarden — not in chat history, git, or screenshots). Treat it like any shared credential.

> ⚠️ **Do NOT** put this password in `seed.py`, an env var that ends up in a committed file, or anywhere version-controlled. The helper `ensure_wit_admin_user()` is intentionally hands-off about `is_active` and password — it never overwrites them, so the password you set here persists across `seed_wit_admin_chats` re-runs.

---

## Step 4 — Create `wit_bot` superuser

`wit_bot` is the **admin account** (Django superuser) and the **author of all daily questions**. It is conceptually distinct from `wit_admin` (which is the support chat persona). Operators who need Django admin access (`/api/secret/`) sign in as `wit_bot`.

```bash
python manage.py createsuperuser \
    --username wit_bot \
    --email whoami.today.official@gmail.com
```

Django will prompt interactively for the password — type it, never put it in a file or shell-history-visible argument.

Verify:
```bash
python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> b = get_user_model().objects.get(username='wit_bot')
>>> b.is_superuser, b.is_staff, b.is_active
(True, True, True)
```

---

## Step 5 — Reassign question authorship to `wit_bot`

The `qna_question` table has an `author_id` column pointing at whichever user originally seeded the questions (typically the legacy superuser, often `id=1`). Make `wit_bot` the canonical author.

> ⚠️ This UPDATEs every row in `qna_question`. Take a backup first if you don't have point-in-time recovery.

```bash
python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> from qna.models import Question
>>> U = get_user_model()
>>> bot = U.objects.get(username='wit_bot')
>>> # Inspect first
>>> Question.objects.values('author_id').annotate(c=__import__('django.db.models').db.models.Count('id')).order_by('-c')
>>> # If all questions share one author and you want them all moved:
>>> Question.objects.update(author=bot)
>>> # Or, more conservatively, only move questions from a specific old author:
>>> # old = U.objects.get(username='admin')   # whatever the old author was called
>>> # Question.objects.filter(author=old).update(author=bot)
```

Verify:
```bash
>>> Question.objects.exclude(author=bot).count()  # → 0 if all were moved
```

---

## Step 6 — Profile images (optional, can defer)

Both accounts will render with the default colour avatar until you upload images. To match the local dev visual:

**Source assets**
- Base image: `https://raw.githubusercontent.com/ssm0318/WhoamI-Today-frontend/main/public/whoami384.png`
- Silhouette overlay (for `wit_admin`): any generic profile-icon PNG (e.g. https://www.freeiconspng.com/images/profile-icon-png).

**Local generation script** (one-shot, run anywhere with Python + Pillow + numpy):
```python
from PIL import Image
import numpy as np

base = Image.open('whoami384.png').convert('RGBA')
silhouette = Image.open('profile-icon.png').convert('RGBA')

# Recolour silhouette to light grey (#E0E0E0)
arr = np.array(silhouette)
mask = arr[..., 3] > 0
arr[mask, 0] = 0xE0; arr[mask, 1] = 0xE0; arr[mask, 2] = 0xE0
sil_grey = Image.fromarray(arr, 'RGBA')

# Resize to 60% of canvas, centred
W, H = base.size
target = int(W * 0.60)
sil_resized = sil_grey.resize((target, target), Image.LANCZOS)
overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
overlay.paste(sil_resized, ((W - target) // 2, (H - target) // 2), sil_resized)
Image.alpha_composite(base, overlay).save('wit_admin_avatar.png')

# wit_bot: just the base
base.save('wit_bot_avatar.png')
```

**Upload via Django admin**:
1. Sign in to `/api/secret/` as `wit_bot`.
2. Navigate to Users → `wit_admin` → set `profile_image` → upload `wit_admin_avatar.png` → save.
3. Same for `wit_bot` with `wit_bot_avatar.png`.

Or, scripted via shell:
```python
from django.contrib.auth import get_user_model
from django.core.files import File
U = get_user_model()
for username, path in [('wit_admin', 'wit_admin_avatar.png'),
                       ('wit_bot', 'wit_bot_avatar.png')]:
    u = U.objects.get(username=username)
    with open(path, 'rb') as f:
        u.profile_image.save(f'{username}.png', File(f), save=True)
```

> Note: the project's `OverwriteStorage` does not actually overwrite — Django will append a hash suffix if the filename already exists. If you re-upload, you may need to manually rename / delete the old file on disk and re-point the DB column. Easier: only upload once per environment, or use a different filename each time.

---

## Verification (after all 6 steps)

Run a smoke test as an admin (e.g. via `python manage.py shell`):

```python
from django.contrib.auth import get_user_model
from chat.models import ChatRoom, Message
from chat.wit_admin import ensure_wit_admin_user, resolve_operators

U = get_user_model()
wit = ensure_wit_admin_user()
assert wit.has_usable_password(), "wit_admin password not set (step 3 missed)"

ops = resolve_operators()
assert len(ops) == 3, "operator users missing"

bot = U.objects.get(username='wit_bot')
assert bot.is_superuser and bot.is_staff, "wit_bot not configured as admin"

# Pick a regular user and verify their rooms
sample = U.objects.exclude(username__in=['wit_admin', 'wit_bot'])\
                  .exclude(email__in=[op.email for op in ops])\
                  .filter(is_active=True).first()
from django.db.models import Q
rooms = ChatRoom.objects.filter(Q(user1=sample) | Q(user2=sample))
print(f"{sample.username}: {rooms.count()} rooms "
      f"({rooms.filter(is_wit_admin_proxy=True).count()} proxy + "
      f"{rooms.exclude(is_wit_admin_proxy=True).count()} non-proxy)")
# Expect: 4 rooms total, 3 proxy + 1 user↔wit_admin
```

Then sign in to the frontend as the sample user and confirm:
- The "WIT Admin" chat is pinned at the top of the chat list.
- The 3 per-operator proxy rooms are NOT visible (they only appear in the operators' lists).

---

## Rollback

If something goes wrong:

1. **Schema rollback** (extremely unlikely to be needed): `python manage.py migrate chat 0009`. This reverses the 3 new migrations. The boolean flag columns will be dropped.
2. **Data rollback** (questions): if step 5 went wrong, restore from the backup taken at pre-flight.
3. **Disable the fan-out** without rolling back schema: comment out the `@receiver` decorator on `fanout_wit_admin_messages` in `adoorback/chat/models.py` and redeploy. Existing rooms remain but no new mirror messages are produced.
4. **Lock `wit_admin`** if its password leaks: open shell, `u = U.objects.get(username='wit_admin'); u.set_unusable_password(); u.is_active = False; u.save()`. Operators lose login until you set a new password.

---

## Maintenance

- **New operators / changed operator emails:** edit the constants `OPERATOR_REPLIER_EMAIL` and `OPERATOR_OBSERVER_EMAILS` in `adoorback/chat/wit_admin.py`, deploy, then re-run `python manage.py seed_wit_admin_chats`.
- **Disable WIT Admin temporarily:** set `wit_admin.is_active = False` via shell. The chat will still appear in lists (because of the pin annotation) but operators can't log in.
- **Audit:** all mirror messages have `is_wit_admin_mirror=True` (`SELECT COUNT(*) FROM chat_message WHERE is_wit_admin_mirror;`). Original user/jaewon messages do not.
