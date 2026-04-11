"""
Clean up old 'ping' and legacy 'chat' app tables and migration records.
This migration runs on remote/production to handle the app rename.
"""
from django.db import migrations


def cleanup_old_apps(apps, schema_editor):
    """Remove old ping and legacy chat tables + migration/content_type records."""
    connection = schema_editor.connection
    cursor = connection.cursor()

    # 1. Clean up notifications referencing old ping content types
    cursor.execute("""
        DELETE FROM notification_notificationactor
        WHERE notification_id IN (
            SELECT n.id FROM notification_notification n
            JOIN django_content_type ct ON n.target_type_id = ct.id
            WHERE ct.app_label = 'ping'
        )
    """)
    cursor.execute("""
        DELETE FROM notification_notification
        WHERE target_type_id IN (
            SELECT id FROM django_content_type WHERE app_label = 'ping'
        )
    """)

    # 2. Drop old ping tables
    cursor.execute("DROP TABLE IF EXISTS ping_pingrequest CASCADE")
    cursor.execute("DROP TABLE IF EXISTS ping_ping CASCADE")
    cursor.execute("DROP TABLE IF EXISTS ping_pingroom CASCADE")

    # 3. Drop old legacy chat tables that DON'T conflict with new schema
    # Note: chat_message and chat_chatroom are reused by the new app — do NOT drop them
    cursor.execute("DROP TABLE IF EXISTS chat_userchatactivity CASCADE")
    cursor.execute("DROP TABLE IF EXISTS chat_messagelike CASCADE")
    cursor.execute("DROP TABLE IF EXISTS chat_chatroom_users CASCADE")

    # 4. Clean up old migration records
    cursor.execute("DELETE FROM django_migrations WHERE app = 'ping'")
    # Remove only old chat migrations (before our fresh 0001_initial)
    cursor.execute("""
        DELETE FROM django_migrations
        WHERE app = 'chat' AND name NOT IN ('0001_initial', '0002_cleanup_old_apps')
    """)

    # 5. Clean up permissions and content types for ping app
    cursor.execute("""
        DELETE FROM auth_permission
        WHERE content_type_id IN (SELECT id FROM django_content_type WHERE app_label = 'ping')
    """)
    cursor.execute("DELETE FROM django_content_type WHERE app_label = 'ping'")


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(cleanup_old_apps, migrations.RunPython.noop),
    ]
