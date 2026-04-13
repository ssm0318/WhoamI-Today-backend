# GitHub Action 배포 개선 가이드

> **배경**: 2026-04-13 migration 문제를 바탕으로 더 안전한 배포 프로세스 구축

## 🔄 현재 vs 개선된 GitHub Action

### 현재 배포 프로세스 문제점
```yaml
# 현재: .github/workflows/deploy-production.yaml
echo "🔄 새 컨테이너 기동"
docker compose -f docker-compose.production.yml up -d
echo "✅ 배포 완료!"
```

**문제점**:
- ❌ Migration 실패 시 감지 못함
- ❌ DB 백업 없음
- ❌ 롤백 계획 없음
- ❌ 배포 후 검증 없음

### 개선된 배포 프로세스
```yaml
# 개선: 안전 검사 + 자동 롤백
echo "🔒 DB 백업 생성"
BACKUP_FILE="backup_$(date +%Y%m%d_%H%M%S).sql"
docker compose exec -T db pg_dump -U postgres whoamitoday > "$BACKUP_FILE"

echo "🧪 Migration Dry Run 테스트"
docker compose exec -T web python manage.py migrate --dry-run --verbosity=2

echo "🚀 Migration 실행"
docker compose exec -T web python manage.py migrate --verbosity=2

echo "✅ 배포 후 검증"
curl -f http://localhost:8000/api/health/ || {
  echo "❌ 롤백 시작"
  docker compose exec -T db psql -U postgres whoamitoday < "$BACKUP_FILE"
  exit 1
}
```

## 📋 개선된 GitHub Action 적용 방법

### 1단계: 기존 파일 백업
```bash
cd ~/WhoamI-Today-backend/.github/workflows/
cp deploy-production.yaml deploy-production-backup-$(date +%Y%m%d).yaml
```

### 2단계: 개선된 워크플로우 파일 생성
```bash
# 새로운 개선된 파일 생성
cat > deploy-production-improved.yaml << 'EOF'
name: Deploy Backend to Production Server (Improved)

on:
  push:
    branches:
      - release/final-research
  workflow_dispatch:

concurrency:
  group: deploy-backend-production
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Connect to EC2 and Deploy
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.NEW_SERVER_HOST }}
          username: ${{ secrets.NEW_SERVER_USER }}
          key: ${{ secrets.NEW_SERVER_KEY }}
          command_timeout: 30m
          script: |
            set -e

            echo "🚀 코드 업데이트"
            cd ~/WhoamI-Today-backend
            git fetch --all --prune
            git checkout ${{ github.ref_name }}
            git reset --hard origin/${{ github.ref_name }}

            echo "🔍 Migration 상태 사전 확인"
            docker compose -f docker-compose.production.yml exec -T web python manage.py showmigrations --plan || echo "컨테이너 미실행 상태"
            
            echo "📋 새로운 migration 파일 확인"
            find . -name "*.py" -path "*/migrations/*" -newer .git/FETCH_HEAD 2>/dev/null || echo "새로운 migration 없음"

            echo "🔒 DB 백업 생성"
            BACKUP_FILE="backup_$(date +%Y%m%d_%H%M%S).sql"
            docker compose -f docker-compose.production.yml exec -T db pg_dump -U postgres whoamitoday > "$BACKUP_FILE"
            echo "백업 완료: $BACKUP_FILE"

            echo "🧹 디스크 정리"
            df -h / | tail -1
            docker builder prune -f --filter "until=72h" || true
            docker image prune -f || true

            echo "🏗️ 이미지 빌드"
            docker compose -f docker-compose.production.yml build

            echo "🛑 기존 컨테이너 종료"
            docker compose -f docker-compose.production.yml down

            echo "🔄 새 컨테이너 시작"
            docker compose -f docker-compose.production.yml up -d

            echo "⏳ 컨테이너 준비 대기"
            timeout 60 bash -c 'until docker compose -f docker-compose.production.yml exec -T web python manage.py check --database default; do sleep 2; done' || {
              echo "❌ 컨테이너 시작 실패 - 롤백"
              docker compose -f docker-compose.production.yml down
              docker compose -f docker-compose.production.yml exec -T db psql -U postgres whoamitoday < "$BACKUP_FILE"
              git reset --hard HEAD~1
              docker compose -f docker-compose.production.yml up --build -d
              exit 1
            }

            echo "🧪 Migration 테스트"
            docker compose -f docker-compose.production.yml exec -T web python manage.py migrate --dry-run --verbosity=2

            echo "🚀 Migration 실행"
            docker compose -f docker-compose.production.yml exec -T web python manage.py migrate --verbosity=2

            echo "✅ 배포 검증"
            docker compose -f docker-compose.production.yml exec -T web python manage.py check --database default
            
            sleep 5
            curl -f http://localhost:8000/api/health/ || {
              echo "❌ API 실패 - 롤백"
              docker compose -f docker-compose.production.yml exec -T db psql -U postgres whoamitoday < "$BACKUP_FILE"
              exit 1
            }

            echo "📊 최종 상태"
            docker compose -f docker-compose.production.yml exec -T web python manage.py showmigrations
            df -h / | tail -1
            echo "🗂️ 백업: ~/$BACKUP_FILE"
EOF
```

### 3단계: 기존 파일 교체
```bash
# 기존 파일을 새 파일로 교체
mv deploy-production.yaml deploy-production-old.yaml
mv deploy-production-improved.yaml deploy-production.yaml
```

### 4단계: 변경사항 커밋
```bash
git add .github/workflows/
git commit -m "feat: improve GitHub Action with migration safety checks

- Add automatic DB backup before deployment
- Add migration dry-run testing
- Add automatic rollback on failure  
- Add post-deployment health checks
- Add detailed logging for debugging"

git push origin release/final-research
```

## 🔧 추가 개선 사항

### 1. Slack/Discord 알림 추가
```yaml
- name: Notify Deployment Status
  if: always()
  run: |
    if [ $? -eq 0 ]; then
      STATUS="✅ 성공"
      COLOR="good"
    else
      STATUS="❌ 실패"
      COLOR="danger"
    fi
    
    curl -X POST ${{ secrets.SLACK_WEBHOOK_URL }} \
      -H 'Content-type: application/json' \
      --data "{
        \"text\": \"🚀 배포 $STATUS\",
        \"attachments\": [{
          \"color\": \"$COLOR\",
          \"fields\": [
            {\"title\": \"브랜치\", \"value\": \"${{ github.ref_name }}\", \"short\": true},
            {\"title\": \"커밋\", \"value\": \"${{ github.sha }}\", \"short\": true},
            {\"title\": \"시간\", \"value\": \"$(date)\", \"short\": false}
          ]
        }]
      }"
```

### 2. 환경별 배포 분리
```yaml
# .github/workflows/deploy-staging.yaml (스테이징용)
on:
  push:
    branches:
      - develop
      - feature/*

# .github/workflows/deploy-production.yaml (프로덕션용)  
on:
  push:
    branches:
      - release/final-research
      - main
```

### 3. 수동 승인 단계 추가
```yaml
jobs:
  approve:
    runs-on: ubuntu-latest
    steps:
      - name: Manual Approval
        uses: trstringer/manual-approval@v1
        with:
          secret: ${{ github.TOKEN }}
          approvers: gina-park,team-lead
          minimum-approvals: 1
          issue-title: "Production 배포 승인 요청"
          
  deploy:
    needs: approve
    runs-on: ubuntu-latest
    # ... 배포 스텝들
```

## 📊 배포 모니터링 개선

### 1. 배포 시간 추적
```bash
# 배포 시작 시간 기록
DEPLOY_START=$(date +%s)

# ... 배포 과정 ...

# 배포 완료 시간 계산
DEPLOY_END=$(date +%s)
DEPLOY_TIME=$((DEPLOY_END - DEPLOY_START))
echo "⏱️ 총 배포 시간: ${DEPLOY_TIME}초"
```

### 2. 리소스 사용량 모니터링
```bash
echo "📊 배포 전 리소스 상태:"
docker stats --no-stream
free -h
df -h

# ... 배포 과정 ...

echo "📊 배포 후 리소스 상태:"
docker stats --no-stream  
free -h
df -h
```

### 3. 에러 로그 자동 수집
```bash
echo "🔍 배포 중 에러 로그 수집:"
docker logs whoami-backend --since="5m" | grep -i "error\|exception\|traceback" > deployment_errors.log
if [ -s deployment_errors.log ]; then
  echo "⚠️ 에러 발견:"
  cat deployment_errors.log
else
  echo "✅ 에러 없음"
fi
```

## 🎯 다음 단계 로드맵

### 1주일 내
- [ ] 개선된 GitHub Action 적용
- [ ] 첫 배포로 동작 확인
- [ ] 팀에 새로운 프로세스 공유

### 1개월 내  
- [ ] Slack/Discord 알림 연동
- [ ] 스테이징 환경 배포 자동화
- [ ] 배포 대시보드 구축

### 3개월 내
- [ ] Blue-Green 배포 도입
- [ ] 자동 성능 테스트 연동
- [ ] 장애 복구 자동화

---

**적용 우선순위**: 
1. 🔥 **즉시**: 개선된 GitHub Action 적용
2. 📊 **1주일**: 모니터링 강화  
3. 🚀 **1개월**: 고도화 기능 추가