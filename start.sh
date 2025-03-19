#!/bin/bash

# DB 마이그레이션
python manage.py migrate

# 슈퍼유저 생성 (환경 변수를 사용)
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "Creating superuser..."
  python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists() or User.objects.create_superuser('$DJANGO_SUPERUSER_USERNAME', '$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_PASSWORD')"
  echo "Superuser created successfully!"
fi

# 개발 서버로 실행 (테스트용)
python manage.py runserver 0.0.0.0:8000

# uwsgi 실행
uwsgi --ini adoorback/.config/uwsgi/uwsgi.ini