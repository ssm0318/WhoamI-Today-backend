#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
import subprocess
from dotenv import load_dotenv
from django.core.management import ManagementUtility
from django.core.management import execute_from_command_line


def main():
    """Run administrative tasks."""
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    # 현재 환경이 Docker 환경인지 확인
    is_runserver_docker = os.path.exists('/.dockerenv')
    print('is_runserver_docker', is_runserver_docker)

    # 중복 출력, 작업 중복 등을 피하기 위해 체크
    is_main_process = os.environ.get('RUN_MAIN') != 'true'
    
    # 현재 디렉토리와 프로젝트 루트 둘 다에서 환경 파일 확인
    # env_file_exists = (os.path.isfile('.env') or 
    #                   os.path.isfile('.env.development') or
    #                   os.path.isfile(os.path.join(project_root, '.env')) or 
    #                   os.path.isfile(os.path.join(project_root, '.env.development')))
    
    # if is_main_process:
    #     print(f"Current directory: {os.getcwd()}")
    #     print(f"Project root directory: {project_root}")
    #     print(f"Environment files exist: {env_file_exists}")
    
    # Docker 환경이 아닌 곳 (ex. 로컬 환경) 에서 runserver 명령어를 사용하는 경우
    if not is_runserver_docker:
        # runserver일 때는 항상 development.py 설정 사용 (환경 변수 강제 설정)
        os.environ['DJANGO_SETTINGS_MODULE'] = 'adoorback.settings.development'
        
        # 로컬 개발을 위해 DB 설정 강제 지정
        os.environ['DB_HOST'] = 'localhost'
        
        if is_main_process:
            print("Using development settings for runserver")
            print("Set DB_HOST to localhost for local development")

        # 데이터베이스 설정은 무조건 postgres 사용
        db_name = os.environ.get('DB_NAME', 'whoamitoday')
        db_user = os.environ.get('DB_USER', 'postgres')
        db_password = os.environ.get('DB_PASSWORD', 'postgres')
        db_host = os.environ.get('DB_HOST', 'localhost')  # 항상 localhost가 될 것임
        
        # Try to create database if it doesn't exist
        db_newly_created = create_database_if_not_exists(db_name, db_user, db_password, db_host)

        # 서버 시작 전 마이그레이션 실행
        print("Running migrations before starting server...")
        migrate_utility = ManagementUtility(['manage.py', 'migrate', '--noinput'])
        migrate_utility.execute()
        print("Migrations completed.")
        
        # 테스트 데이터 로드
        if db_newly_created:
            print("Loading test data before starting server...")
            load_test_data()

    # Docker에서 실행되는 경우
    else:
        # Docker 환경에서는 DJANGO_ENV를 기준으로 환경 설정 결정
        django_env = os.environ.get('DJANGO_ENV', 'development')
        
        if django_env == 'production':
            # Production 환경이면 .env 파일 로드
            if os.path.isfile('.env'):
                load_dotenv('.env', override=True)
                if is_main_process:
                    print("Loaded production settings from .env file")
            elif os.path.isfile(os.path.join(project_root, '.env')):
                load_dotenv(os.path.join(project_root, '.env'), override=True)
                if is_main_process:
                    print("Loaded production settings from project root .env file")
            else:
                if is_main_process:
                    print("Warning: .env file not found for production environment")
        else:
            # Development 환경이면 .env.development 파일 로드
            if os.path.isfile('.env.development'):
                load_dotenv('.env.development', override=True)
                if is_main_process:
                    print("Loaded development settings from .env.development file")
            elif os.path.isfile(os.path.join(project_root, '.env.development')):
                load_dotenv(os.path.join(project_root, '.env.development'), override=True)
                if is_main_process:
                    print("Loaded development settings from project root .env.development file")
            else:
                if is_main_process:
                    print("Warning: .env.development file not found for development environment")
            
            load_test_data()

    execute_from_command_line(sys.argv)
        
    
# Create database if it doesn't exist
def create_database_if_not_exists(db_name, db_user='postgres', db_password='postgres', db_host='localhost'):
    """Create PostgreSQL database if it doesn't exist."""
    try:
        import psycopg2
        print(f"Checking if database '{db_name}' exists on {db_host}...")
        
        # Connect to default database to check if our target DB exists
        conn = psycopg2.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database='postgres'
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'")
        exists = cursor.fetchone()
        
        if not exists:
            print(f"Database '{db_name}' not found. Creating now...")
            cursor.execute(f"CREATE DATABASE {db_name}")
            print(f"Database '{db_name}' created successfully!")
            cursor.close()
            conn.close()
            return True  # Database was newly created
        else:
            print(f"Database '{db_name}' already exists. Continuing...")
            
        cursor.close()
        conn.close()
        return False
    
    except Exception as e:
        print(f"Error checking/creating database: {e}")
        print("Attempting to create database using psql command...")
        try:
            result = subprocess.run(
                ['psql', '-U', db_user, '-h', db_host, '-c', f"CREATE DATABASE {db_name};"],
                capture_output=True,
                text=True,
                env={**os.environ, 'PGPASSWORD': db_password}
            )
            if result.returncode == 0:
                print(f"Database '{db_name}' created successfully using psql!")
                return True  # Database was newly created
            else:
                print(f"Error creating database with psql: {result.stderr}")
                return False
        except Exception as sub_e:
            print(f"Failed to run psql command: {sub_e}")
            return False

# Load test data
def load_test_data():
    """Load test data directly using Django's models and functions."""
    try:
        print("Loading test data...")
        
        # Import Django setup
        import django
        django.setup()
        
        # Import the seed function
        from adoorback.test.seed import set_seed
        print("Running seed function to create test data...")
        
        # Call the set_seed function multiple times as in the script
        # FIXME(GINA) 잠시 주석 처리
        # set_seed(30)
        # for _ in range(3):
        #     try:
        #         set_seed(30)
        #         set_seed(10)
        #         set_seed(20)
        #         set_seed(5)
        #         set_seed(30)
        #     except Exception as e:
                # print(f"Warning: Error during seeding (continuing anyway): {e}")
        
        # Final seed call
        try:
            set_seed(30)
        except Exception as e:
            print(f"Warning: Error during final seeding (continuing anyway): {e}")
            
        # Print some information about created data
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user_count = User.objects.count()
        print(f"Test data loaded successfully! Created {user_count} users.")
        
        # Print out some user emails as verification
        emails = User.objects.values_list('email', flat=True)[:5]
        print(f"Sample user emails: {', '.join(emails)}")
        
        return True
                
    except Exception as e:
        print(f"Error loading test data: {e}")
        return False


if __name__ == '__main__':
    main()