"""Re-author every existing Question row to the wit_bot system user.

Previously the canonical author was an arbitrary superuser (the first one
returned by `User.objects.filter(is_superuser=True).first()`), which leaked
the operator's identity through `is_admin_question = author.is_superuser`
and via any serializer that surfaced the author.
"""
from django.db import migrations


WIT_BOT_USERNAME = 'wit_bot'
WIT_BOT_EMAIL = 'wit.bot@whoami.today'


def _ensure_wit_bot(User):
    """Get-or-create wit_bot on the historical User model.

    Mirrors `chat.wit_bot.ensure_wit_bot_user` minimally without importing
    runtime code (migrations should be self-contained). The historical model
    only exposes `objects`, not the SafeDelete `all_objects` manager — the
    chance of a soft-deleted wit_bot existing at this point in the migration
    history is effectively zero.
    """
    user = User.objects.filter(username=WIT_BOT_USERNAME).first()
    if user is not None:
        if user.email != WIT_BOT_EMAIL:
            user.email = WIT_BOT_EMAIL
            user.save(update_fields=['email'])
        return user
    return User.objects.create(
        username=WIT_BOT_USERNAME,
        email=WIT_BOT_EMAIL,
    )


def reauthor_questions(apps, schema_editor):
    User = apps.get_model('account', 'User')
    Question = apps.get_model('qna', 'Question')
    # No questions to re-author — defer wit_bot creation to the runtime helper.
    # Important: in the test database (which seeds no questions) this keeps
    # wit_bot absent, so existing wit_admin tests that count system connections
    # / per-user rooms aren't disturbed.
    if not Question.objects.exists():
        return
    bot = _ensure_wit_bot(User)
    Question.objects.update(author=bot)


def reverse_reauthor(apps, schema_editor):
    # No-op: original authorship is unrecoverable. The reverse exists so
    # `makemigrations --check` and `migrate <app> <prev>` don't refuse to run.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('qna', '0013_response_image'),
        ('account', '0056_rename_account_fri_evaluat_idx_account_fri_evaluat_a9f25b_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(reauthor_questions, reverse_reauthor),
    ]
