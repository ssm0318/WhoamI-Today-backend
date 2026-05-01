#!/bin/bash

# DB migration
python manage.py migrate

# Create superuser (using environment variables)
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "Creating superuser..."
  python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists() or User.objects.create_superuser('$DJANGO_SUPERUSER_USERNAME', '$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_PASSWORD')"
  echo "Superuser created successfully!"
fi

# Bootstrap WhoamI system accounts (wit_admin, wit_bot, jaewon, koyrkr, njs)
# and provision their chat rooms. Idempotent; safe to re-run.
echo "Bootstrapping system users and chat rooms..."
python manage.py bootstrap_system_users
echo "System bootstrap complete!"

# Run as development server (for testing)
python manage.py runserver 0.0.0.0:8000