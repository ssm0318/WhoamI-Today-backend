# CLAUDE.md - WhoAmI-Today Backend

## Behavioral Guidelines

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

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

---

## Backend-specific architecture

### Spotify (split frontend/backend)
- **Frontend** has a `SpotifyManager` singleton (`WhoamI-Today-frontend/src/libs/SpotifyManager.ts`) that caches resolved tracks in memory and dedups concurrent fetches.
- **Backend has NO `SpotifyManager` class.** Backend uses `_fetch_spotify_oembed()` utility in `check_in/models.py:540` as the oEmbed fallback when API keys are empty (no artist names are available in that mode). Resolved metadata persists in `CheckInComponentEntry.data` JSON.

### Data models
- **CheckIn / Song split:** Song is a separate model from CheckIn. Two API calls: `POST /check_in/` for check-in data, `POST /check_in/song/` for song.
- **CheckIn fields:** `mood` (JSONField, array of up to 5 emojis), `thought` (CharField, max 88), `social_battery`, per-component visibility fields, per-component `*_updated_at` timestamps.
- **Per-component visibility:** `battery_visibility`, `mood_visibility`, `song_visibility`, `thought_visibility` with values `public` / `friends` / `close_friends` / `only_me`. Frontend `ComponentVisibility` enum (`src/models/checkIn.ts`) and backend `VISIBILITY_CHOICES` (`check_in/models.py`) MUST match.
- **Auto-archive:** components with `*_updated_at` > 12 hours ago serialize visibility as `only_me` and data as `null` in the friend API.
- **`CheckInComponentEntry`** (`check_in/models.py:~320–400`): snapshot of one component with its own visibility, JSON `data` payload, plus pin/supersede semantics. Read this before assuming a flat-row design.
- **Poke component types:** `'battery'`, `'mood'`, `'thought'`, `'song'` — NOT `'status'`.

### Feature flags & experiment infra
- **`checkIn` feature flag** is gated by `myProfile.current_ver === 'version_w'`. Test users need `current_ver='version_w'` AND `user_group='group_w_first'` or the CheckIn UI is invisible. If a fresh test user's CheckIn tab/grid doesn't render, that's the first thing to check.
- **`ExperimentLoggingMiddleware`** (`adoorback/experiment_logging/middleware.py`): A/B-testing instrumentation tied to `version_w` / `version_q`. Records which version each request came from. Touch carefully — affects research data collection.

### Notification cleanup TODO (as of 2026-04-30)
When undoing a reaction the corresponding notification should be deleted on backend. Implemented for `Like` only — `Reaction` deletion still leaves notifications behind. If implementing, follow the pattern in `notification/models.py`'s `create_or_update_notification`.

## Verification expectations

Before marking work complete:

- `python manage.py check` — clean, no warnings.
- `python manage.py makemigrations --check` — clean (no pending unapplied schema changes that you forgot to commit).
- For migrations: `python manage.py sqlmigrate <app> <number>` — read the generated SQL and confirm it matches intent. Especially important for `RunPython` migrations and any operation touching tables with prod data.
- For ORM-touching code: run the relevant test suite — `python manage.py test <app>`.
- For data persistence work: open `python manage.py shell`, query the model, confirm the row landed correctly. Don't trust the API's response shape alone — confirm the DB state.

When a save flow is being added or changed:
- Verify via shell that the row exists in the expected state.
- Verify the API endpoint returns the row in the expected shape.
- Restart the backend after model / signal / middleware changes — the dev server doesn't always pick up these changes hot.
