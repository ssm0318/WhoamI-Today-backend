"""
Add group chat support to ChatRoom and make user1/user2/receiver nullable.
Defensive: handles the case where user1_id/user2_id don't exist
(old table reused from legacy app).
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


USER_TABLE = 'account_user'


def column_exists(cursor, table_name, column_name):
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        )
    """, [table_name, column_name])
    return cursor.fetchone()[0]


def constraint_exists(cursor, constraint_name):
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.table_constraints
            WHERE constraint_name = %s
        )
    """, [constraint_name])
    return cursor.fetchone()[0]


def index_exists(cursor, index_name):
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM pg_indexes
            WHERE indexname = %s
        )
    """, [index_name])
    return cursor.fetchone()[0]


def table_exists(cursor, table_name):
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = %s
        )
    """, [table_name])
    return cursor.fetchone()[0]


def forwards(apps, schema_editor):
    cursor = schema_editor.connection.cursor()

    # 1. Remove old constraints that reference user1/user2 (if they exist)
    if constraint_exists(cursor, 'unique_chat_room'):
        cursor.execute("ALTER TABLE chat_chatroom DROP CONSTRAINT unique_chat_room")
    # Also try dropping as index (partial unique indexes show up differently)
    if index_exists(cursor, 'unique_chat_room'):
        cursor.execute("DROP INDEX unique_chat_room")

    if constraint_exists(cursor, 'no_self_chat_room'):
        cursor.execute("ALTER TABLE chat_chatroom DROP CONSTRAINT no_self_chat_room")

    # Drop old index on (user1_id, user2_id) if exists
    if index_exists(cursor, 'chat_chatro_user1_i_3351ba_idx'):
        cursor.execute("DROP INDEX chat_chatro_user1_i_3351ba_idx")

    # 2. Add is_group column if not exists
    if not column_exists(cursor, 'chat_chatroom', 'is_group'):
        cursor.execute(
            "ALTER TABLE chat_chatroom ADD COLUMN is_group boolean NOT NULL DEFAULT false"
        )

    # 3. Add name column if not exists
    if not column_exists(cursor, 'chat_chatroom', 'name'):
        cursor.execute(
            "ALTER TABLE chat_chatroom ADD COLUMN name varchar(100) NOT NULL DEFAULT ''"
        )

    # 4. Add user1_id / user2_id as nullable FK if they don't exist,
    #    or make them nullable if they already exist
    if not column_exists(cursor, 'chat_chatroom', 'user1_id'):
        cursor.execute(f"""
            ALTER TABLE chat_chatroom
            ADD COLUMN user1_id bigint NULL
            REFERENCES "{USER_TABLE}" (id)
            ON DELETE CASCADE
            DEFERRABLE INITIALLY DEFERRED
        """)
        cursor.execute(
            "CREATE INDEX chat_chatroom_user1_id_idx ON chat_chatroom (user1_id)"
        )
    else:
        cursor.execute(
            "ALTER TABLE chat_chatroom ALTER COLUMN user1_id DROP NOT NULL"
        )

    if not column_exists(cursor, 'chat_chatroom', 'user2_id'):
        cursor.execute(f"""
            ALTER TABLE chat_chatroom
            ADD COLUMN user2_id bigint NULL
            REFERENCES "{USER_TABLE}" (id)
            ON DELETE CASCADE
            DEFERRABLE INITIALLY DEFERRED
        """)
        cursor.execute(
            "CREATE INDEX chat_chatroom_user2_id_idx ON chat_chatroom (user2_id)"
        )
    else:
        cursor.execute(
            "ALTER TABLE chat_chatroom ALTER COLUMN user2_id DROP NOT NULL"
        )

    # 5. Create M2M table for members if not exists
    if not table_exists(cursor, 'chat_chatroom_members'):
        cursor.execute(f"""
            CREATE TABLE chat_chatroom_members (
                id bigserial PRIMARY KEY,
                chatroom_id bigint NOT NULL
                    REFERENCES chat_chatroom (id)
                    ON DELETE CASCADE
                    DEFERRABLE INITIALLY DEFERRED,
                user_id bigint NOT NULL
                    REFERENCES "{USER_TABLE}" (id)
                    ON DELETE CASCADE
                    DEFERRABLE INITIALLY DEFERRED
            )
        """)
        cursor.execute(
            "CREATE INDEX chat_chatroom_members_chatroom_id_idx "
            "ON chat_chatroom_members (chatroom_id)"
        )
        cursor.execute(
            "CREATE INDEX chat_chatroom_members_user_id_idx "
            "ON chat_chatroom_members (user_id)"
        )
        cursor.execute("""
            ALTER TABLE chat_chatroom_members
            ADD CONSTRAINT chat_chatroom_members_unique UNIQUE (chatroom_id, user_id)
        """)

    # 6. Make message.receiver_id nullable if it exists
    if column_exists(cursor, 'chat_message', 'receiver_id'):
        cursor.execute(
            "ALTER TABLE chat_message ALTER COLUMN receiver_id DROP NOT NULL"
        )

    # 7. Re-add constraints with new conditions
    if not constraint_exists(cursor, 'unique_chat_room') and not index_exists(cursor, 'unique_chat_room'):
        cursor.execute("""
            CREATE UNIQUE INDEX unique_chat_room
            ON chat_chatroom (user1_id, user2_id)
            WHERE deleted IS NULL AND is_group = false
        """)

    if not index_exists(cursor, 'chat_chatro_user1_i_3351ba_idx'):
        cursor.execute(
            "CREATE INDEX chat_chatro_user1_i_3351ba_idx "
            "ON chat_chatroom (user1_id, user2_id)"
        )

    if not constraint_exists(cursor, 'no_self_chat_room'):
        cursor.execute("""
            ALTER TABLE chat_chatroom
            ADD CONSTRAINT no_self_chat_room CHECK (user1_id != user2_id)
        """)


def backwards(apps, schema_editor):
    """Best-effort reverse."""
    cursor = schema_editor.connection.cursor()

    if constraint_exists(cursor, 'unique_chat_room'):
        try:
            cursor.execute("ALTER TABLE chat_chatroom DROP CONSTRAINT unique_chat_room")
        except Exception:
            cursor.execute("DROP INDEX IF EXISTS unique_chat_room")

    if table_exists(cursor, 'chat_chatroom_members'):
        cursor.execute("DROP TABLE chat_chatroom_members CASCADE")

    for col in ('is_group', 'name'):
        if column_exists(cursor, 'chat_chatroom', col):
            cursor.execute(f"ALTER TABLE chat_chatroom DROP COLUMN {col}")


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("chat", "0003_message_shared_content_type_message_shared_object_id"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(forwards, backwards),
            ],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="chatroom",
                    name="unique_chat_room",
                ),
                migrations.AddField(
                    model_name="chatroom",
                    name="is_group",
                    field=models.BooleanField(default=False),
                ),
                migrations.AddField(
                    model_name="chatroom",
                    name="members",
                    field=models.ManyToManyField(
                        blank=True, related_name="group_chat_rooms", to=settings.AUTH_USER_MODEL
                    ),
                ),
                migrations.AddField(
                    model_name="chatroom",
                    name="name",
                    field=models.CharField(blank=True, default="", max_length=100),
                ),
                migrations.AlterField(
                    model_name="chatroom",
                    name="user1",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_rooms_as_user1",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterField(
                    model_name="chatroom",
                    name="user2",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_rooms_as_user2",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterField(
                    model_name="message",
                    name="receiver",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="received_messages",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AddConstraint(
                    model_name="chatroom",
                    constraint=models.UniqueConstraint(
                        condition=models.Q(("deleted__isnull", True), ("is_group", False)),
                        fields=("user1", "user2"),
                        name="unique_chat_room",
                    ),
                ),
            ],
        ),
    ]
