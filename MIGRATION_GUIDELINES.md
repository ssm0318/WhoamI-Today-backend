# Django Migration 안전 가이드라인

> **목적**: 오늘(2026-04-13) 발생한 migration 문제를 방지하고, Claude/AI가 안전한 migration을 작성할 수 있도록 가이드 제공

## 🚨 오늘 발생한 문제 요약

### 문제 상황
- `0002_cleanup_old_apps.py`에서 "기존 테이블 재사용" 시도
- 실제 프로덕션 DB는 2024년 이전의 매우 오래된 스키마
- 새로운 코드는 2026년 스키마를 기대 → 스키마 불일치로 migration 실패

### 해결 과정
```sql
-- 수동으로 누락된 컬럼들 추가
ALTER TABLE chat_chatroom ADD COLUMN user1_id INTEGER;
ALTER TABLE chat_chatroom ADD COLUMN user2_id INTEGER;
ALTER TABLE chat_chatroom ADD COLUMN is_group BOOLEAN DEFAULT FALSE;
ALTER TABLE chat_chatroom ADD COLUMN name VARCHAR(100) DEFAULT '';

ALTER TABLE chat_message ADD COLUMN is_read BOOLEAN DEFAULT FALSE;
ALTER TABLE chat_message ADD COLUMN receiver_id INTEGER;
ALTER TABLE chat_message ADD COLUMN emoji VARCHAR(20);

-- 기본값 설정
ALTER TABLE chat_chatroom ALTER COLUMN active SET DEFAULT TRUE;
```

## 📋 Migration 작성 시 절대 금지 사항

### ❌ 1. 기존 테이블 "재사용" 가정하지 말기
```python
# 절대 금지!
def cleanup_migration(apps, schema_editor):
    # Note: existing_table은 재사용 — do NOT drop
    cursor.execute("DROP TABLE other_table CASCADE")
    # 기존 테이블 구조를 확인하지 않고 재사용 가정
```

**이유**: 프로덕션의 실제 테이블 구조 ≠ 개발자가 생각하는 구조

### ❌ 2. NOT NULL 컬럼을 기본값 없이 추가
```python
# 절대 금지!
migrations.AddField(
    model_name='chatroom',
    name='required_field',
    field=models.CharField(max_length=100),  # null=False, default 없음
)
```

### ❌ 3. 대용량 테이블의 즉시 ALTER
```python
# 절대 금지!
migrations.AlterField(
    model_name='bigtable',  # 수백만 행
    name='field',
    field=models.TextField(),  # 컬럼 타입 변경
)
```

### ❌ 4. 데이터 검증 없이 제약조건 추가
```python
# 절대 금지!
migrations.AddConstraint(
    model_name='model',
    constraint=models.ForeignKey(...),  # 기존 데이터 정합성 확인 안 함
)
```

## ✅ 안전한 Migration 패턴

### 1. 단계별 컬럼 추가 (3단계 접근법)
```python
# ✅ 1단계: nullable로 추가
class Migration(migrations.Migration):
    operations = [
        migrations.AddField(
            model_name='chatroom',
            name='new_field',
            field=models.CharField(max_length=100, null=True, blank=True),
        ),
    ]

# ✅ 2단계: 데이터 채우기 (별도 migration)
class Migration(migrations.Migration):
    operations = [
        migrations.RunPython(populate_new_field_data, migrations.RunPython.noop),
    ]

def populate_new_field_data(apps, schema_editor):
    Model = apps.get_model('app', 'Model')
    for obj in Model.objects.all():
        obj.new_field = 'default_value'
        obj.save()

# ✅ 3단계: NOT NULL 제약조건 추가 (별도 migration)
class Migration(migrations.Migration):
    operations = [
        migrations.AlterField(
            model_name='chatroom',
            name='new_field',
            field=models.CharField(max_length=100),  # 이제 NOT NULL
        ),
    ]
```

### 2. 안전한 테이블 구조 변경
```python
# ✅ 기존 테이블 검증 후 변경
def safe_table_modification(apps, schema_editor):
    connection = schema_editor.connection
    cursor = connection.cursor()
    
    # 1. 현재 테이블 구조 확인
    cursor.execute("""
        SELECT column_name, data_type, is_nullable 
        FROM information_schema.columns 
        WHERE table_name = 'target_table'
    """)
    existing_columns = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
    
    # 2. 필요한 컬럼이 있는지 확인
    if 'required_column' not in existing_columns:
        cursor.execute("ALTER TABLE target_table ADD COLUMN required_column VARCHAR(100)")
    
    # 3. 기본값 설정
    cursor.execute("ALTER TABLE target_table ALTER COLUMN required_column SET DEFAULT 'default'")
```

### 3. 대용량 테이블 안전 처리
```python
# ✅ PostgreSQL CONCURRENT 인덱스
class Migration(migrations.Migration):
    atomic = False  # 중요!
    
    operations = [
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY idx_table_field ON table_name (field_name);",
            reverse_sql="DROP INDEX CONCURRENTLY idx_table_field;"
        ),
    ]
```

## 🔍 Migration 작성 전 체크리스트

### 로컬 개발 환경에서
- [ ] `python manage.py makemigrations --check` 실행
- [ ] `python manage.py migrate --dry-run` 테스트
- [ ] `python manage.py sqlmigrate app_name migration_number` SQL 확인
- [ ] 로컬 DB에서 실제 migration 실행 테스트

### 코드 리뷰 시
- [ ] Migration 파일의 `operations` 각각 검토
- [ ] `RunPython` 함수의 역방향 migration 확인
- [ ] 대용량 테이블 영향도 평가
- [ ] 다운타임 필요 여부 확인

### 배포 전
- [ ] 프로덕션과 유사한 환경에서 테스트
- [ ] DB 백업 계획 수립
- [ ] 롤백 시나리오 준비

## 🛠️ 개선된 GitHub Action 사용법

### 새로운 배포 워크플로우
기존 `.github/workflows/deploy-production.yaml` 대신 개선된 버전 사용:

```yaml
# .github/workflows/deploy-production-improved.yaml
# 주요 개선사항:
# 1. 배포 전 DB 백업 자동 생성
# 2. Migration dry-run 테스트
# 3. 실패 시 자동 롤백
# 4. 배포 후 헬스체크
```

### 사용 방법
1. 기존 파일을 백업: `mv deploy-production.yaml deploy-production-old.yaml`
2. 새 파일로 교체: `mv deploy-production-improved.yaml deploy-production.yaml`
3. 다음 배포부터 자동으로 안전 검사 실행

## 🚀 Claude/AI를 위한 Migration 작성 가이드

### AI에게 Migration 작업 요청 시 포함할 정보
```
Migration 작성 시 다음 사항을 반드시 고려해주세요:

1. 기존 테이블 구조 확인:
   - 현재 프로덕션 DB의 실제 스키마 상태
   - 이전 migration 파일들의 히스토리

2. 안전한 3단계 접근법 사용:
   - 1단계: nullable 컬럼 추가
   - 2단계: 데이터 마이그레이션
   - 3단계: 제약조건 적용

3. 롤백 가능성 고려:
   - 모든 RunPython에 reverse 함수 제공
   - 데이터 손실 방지 로직 포함

4. 성능 고려사항:
   - 대용량 테이블은 CONCURRENT 옵션 사용
   - 인덱스 추가 시 atomic=False 설정
```

### 예시 프롬프트
```
다음 모델 변경을 위한 안전한 migration을 작성해주세요:

모델: ChatRoom
변경사항: active 필드에 기본값 True 추가

조건:
- 기존 데이터 보존 필수
- 3단계 접근법 사용
- 롤백 가능하도록 작성
- 프로덕션 환경 고려

현재 테이블 구조: [실제 구조 정보 제공]
```

## 📚 참고 자료

### Django 공식 문서
- [Migration Operations](https://docs.djangoproject.com/en/stable/ref/migration-operations/)
- [Schema Editor](https://docs.djangoproject.com/en/stable/ref/schema-editor/)

### PostgreSQL 안전 Migration
- [Safe Operations](https://www.postgresql.org/docs/current/sql-altertable.html)
- [CONCURRENT Operations](https://www.postgresql.org/docs/current/sql-createindex.html#SQL-CREATEINDEX-CONCURRENTLY)

### 모니터링 도구
- [Django Health Check](https://django-health-check.readthedocs.io/)
- [Migration Linter](https://github.com/3YOURMIND/django-migration-linter)

---

**마지막 업데이트**: 2026-04-13  
**작성자**: Migration 문제 해결 경험을 바탕으로 작성  
**목적**: 동일한 문제 재발 방지 및 안전한 Migration 문화 정착