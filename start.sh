#!/bin/bash

# DB 마이그레이션
python manage.py migrate

# 개발 서버로 실행 (테스트용)
python manage.py runserver 0.0.0.0:8000

# uwsgi 실행
uwsgi --ini adoorback/.config/uwsgi/uwsgi.ini