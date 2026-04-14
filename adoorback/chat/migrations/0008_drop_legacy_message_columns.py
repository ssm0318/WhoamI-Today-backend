"""
Drop legacy columns from chat_message that no longer exist in the Django model.
The old chat app had a 'timestamp' column (NOT NULL) which blocks new inserts
because the current model doesn't populate it.
"""
from django.db import migrations


def drop_legacy_columns(apps, schema_editor):
    cursor = schema_editor.connection.cursor()

    # Check which legacy columns still exist
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'chat_message'
    """)
    existing = {row[0] for row in cursor.fetchall()}

    # The current model's DB columns (from models.py):
    # id, created_at, updated_at, deleted, deleted_by_cascade,
    # content, emoji, image, is_read, chat_room_id, sender_id, receiver_id,
    # parent_id, shared_content_type_id, shared_object_id
    model_columns = {
        'id', 'created_at', 'updated_at', 'deleted', 'deleted_by_cascade',
        'content', 'emoji', 'image', 'is_read', 'chat_room_id', 'sender_id',
        'receiver_id', 'parent_id', 'shared_content_type_id', 'shared_object_id',
    }

    legacy_columns = existing - model_columns
    # Only drop columns we know are legacy — be explicit to avoid accidents
    safe_to_drop = {'timestamp'}
    to_drop = legacy_columns & safe_to_drop

    for col in to_drop:
        cursor.execute(f'ALTER TABLE chat_message DROP COLUMN "{col}"')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0007_ensure_chatrequest_table'),
    ]

    operations = [
        migrations.RunPython(drop_legacy_columns, noop),
    ]
