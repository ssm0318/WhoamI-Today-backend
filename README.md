# WhoAmI-Today-backend
- managed by Team WhoAmI

## Set Environment Variables
- Python: set environment variables such as `SECRET_KEY`, `DB_PASSWORD`, `EMAIL_HOST_PASSWORD` inside `.zshrc`, `.bashrc`, or `.bash_profile`
- FCM: `backend/adoorback/adoorback/serviceAccountKey.json`

## Run Server
```
# install redis
brew install redis
brew services start redis
```

```
cd adoorback
pip install -r requirements.txt

python manage.py migrate

# seed data
python manage.py shell
from adoorback.test.seed import set_seed
set_seed(20)
exit()

python manage.py runserver
```

psycopg2, mysqlclient
이 두 가지는 requirements.txt에서 제거하고 설치해도 됩니다
```
psycopg2==2.8.6
django-mysql==3.9.0
```


## Drop Postgresql DB
```
psql -U postgres
drop database diivers;
create database diivers with owner postgres;
\q

# need to migrate again
cd adoorback
python manage.py migrate
```

## Test

```
pylint **/*.py --load-plugins pylint_django

python manage.py makemigrations account feed comment like notification user_report content_report
python manage.py migrate

coverage run --source='.' --omit='*/migrations/*','adoorback/*','feed/algorithms/*','feed/cron.py','account/cron.py','locustfile.py','manage.py','*/wsgi.py','*/asgi.py','*/utils/*' ./manage.py test
coverage run --source='.' --branch --omit='*/migrations/*','adoorback/*','feed/algorithms/*','feed/cron.py','account/cron.py','locustfile.py','manage.py','*/wsgi.py','*/asgi.py','*/utils/*' ./manage.py test

coverage report -m

# test only specific model [model_name]
coverage run --source='.' --omit='*/migrations/*','adoorback/*','feed/algorithms/*','feed/cron.py','account/cron.py','locustfile.py','manage.py','*/wsgi.py','*/asgi.py','*/utils/*' ./manage.py test [model_name]
coverage run --source='.' --branch --omit='*/migrations/*','adoorback/*','feed/algorithms/*','feed/cron.py','account/cron.py','locustfile.py','manage.py','*/wsgi.py','*/asgi.py','*/utils/*' ./manage.py test [model_name]
coverage report -m
```

## 백엔드 수동 배포
### A. 서버 접속하기

1. pem 키를 다운로드 받아 적절한 곳 (e.g. `Documents` 폴더)에 넣어준 후 `chmod 400 diivers.pem`을 입력하여 권한설정을 해준다. (pem키는 public하면 안 되기 때문에 읽기 권한을 제외하고 전부 없애주는 것)    
2. pem키가 있는 경로에서 `ssh -i diivers.pem ubuntu@3.39.220.146 을 입력하여 서버에 접속한다. (맨 처음 접속할 때는  `yes`를 입력해줘야 함)

### B. 백엔드 코드 접근하기

1. `source ~/venv3.9/bin/activate`를 입력하여 파이썬 가상환경을 실행한다.
    
    `ubuntu@ip-172-31-19-133` 좌측에 `(venv3.9)`가 생겨야 정상
    
2. 홈 디렉토리에서 `cd WhoAmI-Today-backend`을 입력하여 백엔드 코드가 있는 곳으로 접근한다.

### C. 코드 업데이트하기

1. 깃 브랜치가 `main`으로 되어있는 것을 확인한 후 `git pull` 을 하여 코드를 업데이트한다.
    1. username: 각자의 유저 네임
    2. password: 각자의 깃헙 토큰
2. (백엔드 DB 구조에 변화가 있을 경우) `cd adoorback` 명령으로 `~/WhoAmI-Today-backend/adoorback` 으로 이동한 후 아래 코드를 차례로 입력한다.
    
    ```python
    (설치한 패키지가 있다면) pip install -r requirements.txt
    ./manage.py migrate
    ```
    
3. (이미 인스턴스가 존재하는 백엔드 모델에 번역 필드가 추가된 경우)   `cd adoorback` 명령으로 `~/WhoAmI-Today-backend/adoorback` 으로 이동한 후 아래 코드를 입력한다.
    
    ```bash
    	./manage.py update_translation_fields
    ```
    
4. (백엔드 코드에 변화가 있을 경우) `sudo systemctl restart uwsgi` 을 입력한다.

## 서버 관련 기타 커맨드

1. 백엔드 로그 실시간으로 확인하기 `tail -f /var/log/uwsgi/WhoAmI-Today-backend.log`
2. nginx 상태 확인하기 `sudo systemctl status nginx`
3. db 재시작 `sudo systemctl restart postgresql.service`
