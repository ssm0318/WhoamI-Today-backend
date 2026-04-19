"""
Comprehensive fix: ensure all chat tables and columns exist.
0001_initial was faked on production, so new tables (MessageReaction,
ChatRequest, GroupReadCursor, ChatRoom_members M2M) and new columns
on legacy tables (chat_message, chat_chatroom) may be missing.
All operations are idempotent — safe to run even if some already exist.
"""
from django.conf import settings
from django.db import migrations


def table_exists(cursor, table_name):
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = %s
        )
    """, [table_name])
    return cursor.fetchone()[0]


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


USER_TABLE = 'account_user'


def ensure_all(apps, schema_editor):
    cursor = schema_editor.connection.cursor()

    # =====================================================================
    # 1. chat_messagereaction (from 0001_initial)
    # =====================================================================
    if not table_exists(cursor, 'chat_messagereaction'):
        cursor.execute(f"""
            CREATE TABLE chat_messagereaction (
                id bigserial PRIMARY KEY,
                created_at timestamp with time zone NOT NULL DEFAULT now(),
                updated_at timestamp with time zone NOT NULL DEFAULT now(),
                deleted timestamp with time zone NULL,
                deleted_by_cascade boolean NOT NULL DEFAULT false,
                emoji varchar(20) NOT NULL,
                message_id bigint NOT NULL REFERENCES chat_message (id) DEFERRABLE INITIALLY DEFERRED,
                user_id bigint NOT NULL REFERENCES "{USER_TABLE}" (id) DEFERRABLE INITIALLY DEFERRED
            )
        """)
        cursor.execute("CREATE INDEX chat_messagereaction_message_id_idx ON chat_messagereaction (message_id)")
        cursor.execute("CREATE INDEX chat_messagereaction_user_id_idx ON chat_messagereaction (user_id)")
        cursor.execute("CREATE INDEX chat_messagereaction_deleted_idx ON chat_messagereaction (deleted)")

    if not index_exists(cursor, 'unique_message_reaction'):
        cursor.execute("""
            CREATE UNIQUE INDEX unique_message_reaction
            ON chat_messagereaction (user_id, message_id, emoji)
            WHERE deleted IS NULL
        """)

    # =====================================================================
    # 2. chat_chatroom_members (M2M from 0004)
    # =====================================================================
    if not table_exists(cursor, 'chat_chatroom_members'):
        cursor.execute(f"""
            CREATE TABLE chat_chatroom_members (
                id bigserial PRIMARY KEY,
                chatroom_id bigint NOT NULL REFERENCES chat_chatroom (id) DEFERRABLE INITIALLY DEFERRED,
                user_id bigint NOT NULL REFERENCES "{USER_TABLE}" (id) DEFERRABLE INITIALLY DEFERRED
            )
        """)
        cursor.execute("CREATE INDEX chat_chatroom_members_chatroom_id_idx ON chat_chatroom_members (chatroom_id)")
        cursor.execute("CREATE INDEX chat_chatroom_members_user_id_idx ON chat_chatroom_members (user_id)")
        cursor.execute("""
            ALTER TABLE chat_chatroom_members
            ADD CONSTRAINT chat_chatroom_members_unique UNIQUE (chatroom_id, user_id)
        """)

    # =====================================================================
    # 3. chat_groupreadcursor (from 0006)
    # =====================================================================
    if not table_exists(cursor, 'chat_groupreadcursor'):
        cursor.execute(f"""
            CREATE TABLE chat_groupreadcursor (
                id bigserial PRIMARY KEY,
                chat_room_id bigint NOT NULL REFERENCES chat_chatroom (id) DEFERRABLE INITIALLY DEFERRED,
                last_read_message_id bigint NULL REFERENCES chat_message (id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED,
                user_id bigint NOT NULL REFERENCES "{USER_TABLE}" (id) DEFERRABLE INITIALLY DEFERRED
            )
        """)
        cursor.execute("CREATE INDEX chat_groupreadcursor_chat_room_id_idx ON chat_groupreadcursor (chat_room_id)")
        cursor.execute("CREATE INDEX chat_groupreadcursor_user_id_idx ON chat_groupreadcursor (user_id)")
        cursor.execute("CREATE INDEX chat_groupreadcursor_last_read_message_id_idx ON chat_groupreadcursor (last_read_message_id)")

    if not constraint_exists(cursor, 'unique_group_read_cursor'):
        cursor.execute("""
            ALTER TABLE chat_groupreadcursor
            ADD CONSTRAINT unique_group_read_cursor UNIQUE (user_id, chat_room_id)
        """)

    # =====================================================================
    # 4. Missing columns on chat_chatroom (from 0004)
    # =====================================================================
    if not column_exists(cursor, 'chat_chatroom', 'is_group'):
        cursor.execute("ALTER TABLE chat_chatroom ADD COLUMN is_group boolean NOT NULL DEFAULT false")

    if not column_exists(cursor, 'chat_chatroom', 'name'):
        cursor.execute("ALTER TABLE chat_chatroom ADD COLUMN name varchar(100) NOT NULL DEFAULT ''")

    if not column_exists(cursor, 'chat_chatroom', 'deleted'):
        cursor.execute("ALTER TABLE chat_chatroom ADD COLUMN deleted timestamp with time zone NULL")
        cursor.execute("CREATE INDEX chat_chatroom_deleted_idx ON chat_chatroom (deleted)")

    if not column_exists(cursor, 'chat_chatroom', 'deleted_by_cascade'):
        cursor.execute("ALTER TABLE chat_chatroom ADD COLUMN deleted_by_cascade boolean NOT NULL DEFAULT false")

    # Make user1/user2 nullable (0004 AlterField)
    cursor.execute("""
        ALTER TABLE chat_chatroom ALTER COLUMN user1_id DROP NOT NULL
    """)
    cursor.execute("""
        ALTER TABLE chat_chatroom ALTER COLUMN user2_id DROP NOT NULL
    """)

    # =====================================================================
    # 5. Missing columns on chat_message
    # =====================================================================
    if not column_exists(cursor, 'chat_message', 'emoji'):
        cursor.execute("ALTER TABLE chat_message ADD COLUMN emoji varchar(20) NULL")

    if not column_exists(cursor, 'chat_message', 'parent_id'):
        cursor.execute("ALTER TABLE chat_message ADD COLUMN parent_id bigint NULL REFERENCES chat_message (id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED")
        cursor.execute("CREATE INDEX chat_message_parent_id_idx ON chat_message (parent_id)")

    if not column_exists(cursor, 'chat_message', 'deleted'):
        cursor.execute("ALTER TABLE chat_message ADD COLUMN deleted timestamp with time zone NULL")
        cursor.execute("CREATE INDEX chat_message_deleted_idx ON chat_message (deleted)")

    if not column_exists(cursor, 'chat_message', 'deleted_by_cascade'):
        cursor.execute("ALTER TABLE chat_message ADD COLUMN deleted_by_cascade boolean NOT NULL DEFAULT false")

    if not column_exists(cursor, 'chat_message', 'shared_content_type_id'):
        cursor.execute("ALTER TABLE chat_message ADD COLUMN shared_content_type_id integer NULL REFERENCES django_content_type (id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED")
        cursor.execute("CREATE INDEX chat_message_shared_content_type_id_idx ON chat_message (shared_content_type_id)")

    if not column_exists(cursor, 'chat_message', 'shared_object_id'):
        cursor.execute("ALTER TABLE chat_message ADD COLUMN shared_object_id integer NULL")

    if not column_exists(cursor, 'chat_message', 'image'):
        cursor.execute("ALTER TABLE chat_message ADD COLUMN image varchar(100) NULL")

    # Make receiver nullable (0004 AlterField)
    if column_exists(cursor, 'chat_message', 'receiver_id'):
        cursor.execute("ALTER TABLE chat_message ALTER COLUMN receiver_id DROP NOT NULL")

    # =====================================================================
    # 6. Missing indexes on existing tables
    # =====================================================================
    if not index_exists(cursor, 'chat_messag_chat_ro_bda5c0_idx'):
        cursor.execute("CREATE INDEX chat_messag_chat_ro_bda5c0_idx ON chat_message (chat_room_id, created_at)")

    if not index_exists(cursor, 'chat_messag_receive_14362e_idx'):
        cursor.execute("CREATE INDEX chat_messag_receive_14362e_idx ON chat_message (receiver_id, is_read)")

    if not index_exists(cursor, 'chat_chatro_user1_i_3351ba_idx'):
        cursor.execute("CREATE INDEX chat_chatro_user1_i_3351ba_idx ON chat_chatroom (user1_id, user2_id)")

    # =====================================================================
    # 7. Missing constraints on chat_chatroom
    # =====================================================================
    if not constraint_exists(cursor, 'no_self_chat_room'):
        cursor.execute("""
            ALTER TABLE chat_chatroom
            ADD CONSTRAINT no_self_chat_room CHECK (user1_id != user2_id)
        """)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0008_drop_legacy_message_columns'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(ensure_all, noop),
    ]
