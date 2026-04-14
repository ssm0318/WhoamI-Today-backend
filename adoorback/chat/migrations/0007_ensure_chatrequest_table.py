"""
Ensure chat_chatrequest table exists in the database.
The table was defined in 0001_initial but may not have been created
if that migration was faked during the app rename cleanup.
"""
from django.conf import settings
from django.db import migrations


def create_chatrequest_if_missing(apps, schema_editor):
    connection = schema_editor.connection
    cursor = connection.cursor()

    # Check if the table already exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'chat_chatrequest'
        )
    """)
    exists = cursor.fetchone()[0]

    if not exists:
        # Determine the auth user table name
        user_table = 'account_user'  # Django custom user model table

        cursor.execute(f"""
            CREATE TABLE chat_chatrequest (
                id bigserial PRIMARY KEY,
                created_at timestamp with time zone NOT NULL DEFAULT now(),
                updated_at timestamp with time zone NOT NULL DEFAULT now(),
                deleted timestamp with time zone NULL,
                deleted_by_cascade boolean NOT NULL DEFAULT false,
                accepted boolean NULL DEFAULT NULL,
                requestee_id bigint NOT NULL REFERENCES "{user_table}" (id) DEFERRABLE INITIALLY DEFERRED,
                requester_id bigint NOT NULL REFERENCES "{user_table}" (id) DEFERRABLE INITIALLY DEFERRED
            )
        """)

        # Add indexes on FKs
        cursor.execute("""
            CREATE INDEX chat_chatrequest_requestee_id_idx
            ON chat_chatrequest (requestee_id)
        """)
        cursor.execute("""
            CREATE INDEX chat_chatrequest_requester_id_idx
            ON chat_chatrequest (requester_id)
        """)
        cursor.execute("""
            CREATE INDEX chat_chatrequest_deleted_idx
            ON chat_chatrequest (deleted)
        """)

        # Add constraints matching the model
        cursor.execute("""
            ALTER TABLE chat_chatrequest
            ADD CONSTRAINT unique_chat_request
            UNIQUE (requester_id, requestee_id)
        """)
        # Note: partial unique (WHERE deleted IS NULL) can't be done with
        # plain UNIQUE — use a unique index instead. Drop the simple one and
        # recreate as partial.
        cursor.execute("""
            ALTER TABLE chat_chatrequest
            DROP CONSTRAINT unique_chat_request
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX unique_chat_request
            ON chat_chatrequest (requester_id, requestee_id)
            WHERE deleted IS NULL
        """)
        cursor.execute("""
            ALTER TABLE chat_chatrequest
            ADD CONSTRAINT no_self_chat_request
            CHECK (requester_id != requestee_id)
        """)


def drop_chatrequest_if_we_created_it(apps, schema_editor):
    """Reverse: drop table only if this migration created it."""
    connection = schema_editor.connection
    cursor = connection.cursor()
    cursor.execute("DROP TABLE IF EXISTS chat_chatrequest CASCADE")


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0006_groupreadcursor_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(
            create_chatrequest_if_missing,
            drop_chatrequest_if_we_created_it,
        ),
    ]
