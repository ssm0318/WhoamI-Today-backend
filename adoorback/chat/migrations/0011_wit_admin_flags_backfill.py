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
