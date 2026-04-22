# CLAUDE.md - WhoAmI-Today Backend

## Project Overview
- Django 4.2.14 + DRF backend (`adoorback/`) with PostgreSQL 13
- 실시간: Django Channels 4.0 + Redis 7 (채팅 WebSocket)
- 배포: Docker Compose (app + postgres + redis + cron) + GitHub Actions → AWS EC2
- 도메인: whoami-test-group.gina-park.site (test) / whoami.gina-park.site (prod)

## 아키텍처

### Django Apps (16+)
account, qna, note, chat, notification, comment, like, reaction, check_in, playlist, tracking, translate, custom_fcm, content_report, user_report, user_tag

### 인증
- JWT (cookie `access_token` + Authorization header) — 365일 토큰 수명
- `adoorback/utils/authentication.py` — CustomAuthentication, SessionAuthentication
- CSRF 토큰 검증 포함

### 크론 작업 (django-cron)
- 일일 질문 알림 (사용자 타임존 기반)
- 세션 자동 종료 (2분 타임아웃)
- 체크인 만료 처리

### 버전 시스템 (Ver.Q / Ver.W)
- API: `/api/` (Ver.W) vs `/api/q/` (Ver.Q)
- 사용자 배정: `version_w` / `version_q`
- 실험 로깅: ExperimentLoggingMiddleware

### Base 모델
- `AdoorTimestampedModel`, `AdoorModel` (content validation)
- SafeDeleteModel (soft delete)

### 외부 연동
- Firebase Admin SDK: 푸시 알림 (fcm-django)
- Google Cloud Translate: 콘텐츠 번역
- Slack: 알림 (`adoorback/utils/alerts.py`)
- 관리자 페이지: `/api/secret/` → Django Admin

## Django Migration Safety Rules

Migration 작성 시 반드시 아래 규칙을 따를 것. 2026-04-13에 프로덕션에서 migration 장애가 발생한 경험을 바탕으로 작성됨.

### 절대 금지 사항
1. **기존 테이블 "재사용" 가정 금지** - 프로덕션 DB의 실제 스키마는 코드가 기대하는 구조와 다를 수 있음. 항상 `information_schema.columns`로 현재 구조를 확인할 것.
2. **NOT NULL 컬럼을 기본값 없이 추가 금지** - 기존 행에 값이 없으면 migration 실패함.
3. **대용량 테이블의 즉시 ALTER 금지** - 수백만 행의 컬럼 타입 변경은 lock을 오래 잡음.
4. **데이터 검증 없이 제약조건(FK 등) 추가 금지** - 기존 데이터 정합성부터 확인할 것.

### 안전한 패턴: 3단계 접근법
새 컬럼 추가 시 반드시 3단계로 나눌 것:
1. **1단계**: `null=True, blank=True`로 nullable 컬럼 추가
2. **2단계**: 별도 migration에서 `RunPython`으로 데이터 채우기 (reverse 함수 필수)
3. **3단계**: 별도 migration에서 NOT NULL 제약조건 적용

### 테이블 구조 변경 시
```python
# 반드시 현재 구조를 확인한 후 변경
cursor.execute("""
    SELECT column_name, data_type, is_nullable 
    FROM information_schema.columns 
    WHERE table_name = 'target_table'
""")
existing_columns = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
if 'column_name' not in existing_columns:
    cursor.execute("ALTER TABLE target_table ADD COLUMN column_name ...")
```

### 인덱스 추가 시
- `atomic = False` 설정 필수
- `CREATE INDEX CONCURRENTLY` 사용

### Migration 작성 전 체크
- `python manage.py makemigrations --check`
- `python manage.py sqlmigrate app_name migration_number`로 생성될 SQL 확인
- 모든 `RunPython`에 reverse 함수 제공
- 롤백 시나리오 고려

자세한 내용: `MIGRATION_GUIDELINES.md` 참조

## 코드 컨벤션

### 네이밍
- 필드/변수: **snake_case** (`friend_request`, `current_user_read`)
- 클래스: **PascalCase** (`FriendRequest`, `UserProfileSerializer`)
- 상수: **UPPER_SNAKE_CASE** (`VERSION_CHOICES`, `MAX_GROUP_MEMBERS`)
- related_name: `*_set` (역참조), `*_notis` (GenericRelation), `*_ids` (ID 리스트)

### 모델 패턴
- `AdoorTimestampedModel` / `AdoorModel` 상속 필수
- Soft delete: `SafeDeleteModel` + `_safedelete_policy = SOFT_DELETE_CASCADE`
- `UniqueConstraint`에 `condition=Q(deleted__isnull=True)` 조건 추가
- `@property`로 computed 필드 (`connected_users`, `friend_ids`, `is_audience`)
- `GenericRelation`으로 다형성 관계 (notification, like, comment)
- 리스트 필드: PostgreSQL `ArrayField` 사용

### Serializer 패턴
- `AdoorBaseSerializer` 상속 (comment_count, like_count, current_user_like_id 포함)
- Minimal / Full 분리 (`UserMinimalSerializer` vs `UserProfileSerializer`)
- `HyperlinkedRelatedField` + custom `lookup_field='username'`
- 복잡한 로직: `SerializerMethodField` + `get_xxx()` 메서드
- 커스텀 필드: `VisibilityField(MultipleChoiceField)` 등

### View 패턴
- 간단한 CRUD: `generics.CreateAPIView`, `RetrieveUpdateDestroyAPIView`
- 커스텀 로직: `APIView`
- Permission 스택: `[IsAuthenticated, IsAuthorOrReadOnly, IsShared, IsNotBlocked]`
- 쓰기 작업: `@transaction.atomic` 데코레이터
- `get_object()`에서 `check_object_permissions` + `is_audience` 확인
- 차단 필터링: `ContentReport` / `UserReport` 기반 queryset 제외

### URL 패턴
- RESTful nested: `/api/user/<username>/notes/`, `/api/qna/responses/<pk>/comments/`
- 버전 분리: `/api/` (Ver.W) vs `/api/q/` (Ver.Q) — 각 앱에 `urls.py` + `urls_q.py`

### Signal 패턴
- `@transaction.atomic` + `@receiver(post_save, sender=Model)`
- 알림 생성, 관계 정리, 파일 삭제 등에 사용
- `post_delete` signal로 파일 cleanup

### 에러 처리
- `APIException` 상속 커스텀 예외 (`ExistingUsername`, `InActiveUser`)
- `adoor_exception_handler`에서 Slack 알림 분기 (사용자 입력 에러는 제외)
- 검증: `AdoorUsernameValidator` (한글 지원 regex)

### 테스트 패턴
- `TestCase` + `setUp()`에서 User/Connection 생성
- `APIClient` + `force_authenticate(user=self.user)`
- `APIRequestFactory`로 serializer context 테스트
