FROM python:3.9-slim

WORKDIR /app

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    python3-dev \
    postgresql-server-dev-all \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# pip 업그레이드
RUN pip install --upgrade pip

# 시작 스크립트
COPY start.sh .
RUN chmod +x /app/start.sh  # 전체 경로 사용
RUN ls -la /app/start.sh    # 권한 확인용

# 프로젝트 파일 복사 - 중첩된 디렉토리 구조 방지
COPY adoorback /app/adoorback
COPY docker-compose.* .
COPY init.sql .
COPY .env* .
COPY .dockerignore .
COPY .gitignore .

# 파이썬 패키지 설치
WORKDIR /app/adoorback
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install uwsgi

# 작업 디렉토리 유지
WORKDIR /app/adoorback

# 포트 설정
EXPOSE 8000

# 환경 변수 설정
ENV PYTHONUNBUFFERED=1

# 슈퍼유저 생성을 위한 환경 변수 (실제 배포 시 수정 필요)
ENV DJANGO_SUPERUSER_USERNAME=admin
ENV DJANGO_SUPERUSER_EMAIL=admin@example.com
ENV DJANGO_SUPERUSER_PASSWORD=adminpassword

CMD ["/app/start.sh"]