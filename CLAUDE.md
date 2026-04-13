# CLAUDE.md - WhoAmI-Today Backend

## Project Overview
- Django backend (`adoorback/`) with PostgreSQL
- Deployed via Docker + GitHub Actions to production

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
