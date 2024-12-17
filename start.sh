#!/bin/bash

# DB 마이그레이션
python manage.py migrate

# 개발 서버로 실행 (테스트용)
python manage.py runserver 0.0.0.0:8000

# uwsgi는 나중에 설정이 완료되면 사용
# uwsgi --ini .config/uwsgi/uwsgi.ini