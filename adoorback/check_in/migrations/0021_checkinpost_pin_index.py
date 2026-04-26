from django.db import migrations, models


class Migration(migrations.Migration):
    """Add (author, is_pinned) index using CREATE INDEX CONCURRENTLY.

    Per CLAUDE.md migration safety: index additions on tables that may grow
    must use CONCURRENTLY to avoid holding a write lock. This migration is
    therefore non-atomic and uses SeparateDatabaseAndState so Django's model
    state matches the actual DB index.
    """

    atomic = False

    dependencies = [
        ('check_in', '0020_checkinpost_pin_fields'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                        "check_in_ch_author_pinned_idx "
                        "ON check_in_checkinpost (author_id, is_pinned);"
                    ),
                    reverse_sql="DROP INDEX IF EXISTS check_in_ch_author_pinned_idx;",
                ),
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name='checkinpost',
                    index=models.Index(
                        fields=['author', 'is_pinned'],
                        name='check_in_ch_author_pinned_idx',
                    ),
                ),
            ],
        ),
    ]
