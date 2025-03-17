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

    # 현재 환경이 Docker 환경인지 확인
    is_runserver_docker = os.path.exists('/.dockerenv')
    print('is_runserver_docker', is_runserver_docker)

    # 현재 환경이 production인지 확인
    is_production = os.getenv('DJANGO_ENV', 'development') == 'production'

    # local
    if not is_runserver_docker:  
        os.environ['DJANGO_ENV'] = 'development'
        os.environ['DB_HOST'] = 'localhost'
        db_host = 'localhost'

    # docker compose > development
    elif not is_production:
        load_dotenv('.env.development', override=True)
        
        # force db host
        db_host = 'db'
    
    # docker compose > production
    else:
        load_dotenv('.env', override=True)
        # Get DB_HOST from environment or default to 'db' if not provided
        db_host = os.environ.get('DB_HOST', 'db')

    db_name = os.environ.get('DB_NAME', 'whoamitoday')
    db_user = os.environ.get('DB_USER', 'postgres')
    db_password = os.environ.get('DB_PASSWORD', 'postgres')
        
    # Try to create database if it doesn't exist
    db_newly_created = create_database_if_not_exists(db_name, db_user, db_password, db_host)

    # run migrations
    print("Running migrations before starting server...")
    migrate_utility = ManagementUtility(['manage.py', 'migrate', '--noinput'])
    migrate_utility.execute()
    print("Migrations completed.")
    
    # load test data only when database is newly created
    if db_newly_created:
        print("Loading test data before starting server...")
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
        set_seed(30)
        for _ in range(3):
            try:
                set_seed(30)
                set_seed(10)
                set_seed(20)
                set_seed(5)
                set_seed(30)
            except Exception as e:
                print(f"Warning: Error during seeding (continuing anyway): {e}")
        
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