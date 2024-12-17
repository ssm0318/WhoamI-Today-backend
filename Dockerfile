FROM python:3.9-slim

WORKDIR /app

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
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

# 프로젝트 파일 복사
COPY . .

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

CMD ["/app/start.sh"]