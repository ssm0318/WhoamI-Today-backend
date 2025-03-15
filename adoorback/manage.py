#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
import subprocess
from dotenv import load_dotenv

def create_database_if_not_exists(db_name, db_user='postgres', db_password='postgres'):
    """Create PostgreSQL database if it doesn't exist."""
    try:
        import psycopg2
        print(f"Checking if database '{db_name}' exists...")
        
        # Connect to default database to check if our target DB exists
        conn = psycopg2.connect(
            host='localhost',
            user=db_user,
            password=db_password,
            database='postgres'  # Connect to default DB first
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
        else:
            print(f"Database '{db_name}' already exists. Continuing...")
            
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error creating database: {e}")
        print("Attempting to create database using psql command...")
        try:
            result = subprocess.run(
                ['psql', '-U', db_user, '-c', f"CREATE DATABASE {db_name};"],
                capture_output=True,
                text=True,
                env={**os.environ, 'PGPASSWORD': db_password}
            )
            if result.returncode == 0:
                print(f"Database '{db_name}' created successfully using psql!")
                return True
            else:
                print(f"Error creating database with psql: {result.stderr}")
                return False
        except Exception as sub_e:
            print(f"Failed to run psql command: {sub_e}")
            return False

def load_test_data():
    """Load test data directly using Django's models and functions."""
    try:
        print("Loading test data...")
        
        # Get the path to the shell script file
        shell_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                        'adoorback', 'test', 'shell')
        
        # Check if the file exists
        if not os.path.exists(shell_script_path):
            print(f"Test script not found at: {shell_script_path}")
            return False
            
        # Read the content of the shell script and execute it directly
        print("Importing required models and functions...")
        
        # Import Django setup
        import django
        django.setup()
        
        # Import all models and functions needed
        from django.contrib.auth import get_user_model
        from rest_framework_simplejwt.tokens import RefreshToken
        
        # Try to import the seed function
        try:
            from adoorback.test.seed import set_seed
            print("Running seed function to create test data...")
            
            # Call the set_seed function multiple times as in the script
            for i in range(3):
                set_seed(30)
                set_seed(10)
                set_seed(20)
                set_seed(5)
                set_seed(30)
            
            # Final seed call
            set_seed(30)
            
            # Print some information about created data
            User = get_user_model()
            user_count = User.objects.count()
            print(f"Test data loaded successfully! Created {user_count} users.")
            
            # Print out some user emails as verification
            emails = User.objects.values_list('email', flat=True)[:5]
            print(f"Sample user emails: {', '.join(emails)}")
            
            return True
        except ImportError as e:
            print(f"Could not import seed function: {e}")
            print("Attempting to run shell script directly...")
            
            # Fallback to running the script using subprocess
            result = subprocess.run(
                ['python3', 'manage.py', 'shell', '<', shell_script_path],
                shell=True,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print("Test data loaded using shell script.")
                return True
            else:
                print(f"Error running shell script: {result.stderr}")
                return False
                
    except Exception as e:
        print(f"Error loading test data: {e}")
        return False

def main():
    """Run administrative tasks."""
    
    # Check if testing with SKIP_ENV_FILE flag is active
    skip_env_file = os.environ.get('SKIP_ENV_FILE', 'False').lower() in ('true', '1', 't')
    is_runserver = 'runserver' in sys.argv
    
    # Only print environment logs for the main process, not for Django's auto-reloader
    is_main_process = os.environ.get('RUN_MAIN') != 'true'

    # Set Django settings module - prefer development in local environment
    if is_runserver or skip_env_file:
        os.environ['DJANGO_SETTINGS_MODULE'] = 'adoorback.settings.development'
        if is_main_process:
            print(f"Running in DEVELOPMENT environment (runserver={is_runserver}, skip_env={skip_env_file})")
    else:
        # For other commands, check if env file exists and determine environment
        if os.path.isfile('.env') and not skip_env_file:
            # Load .env file for production settings if it exists
            load_dotenv('.env', override=True)
            if is_main_process:
                print("Running in PRODUCTION environment (from .env file)")
        else:
            # Default to development settings
            os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'adoorback.settings.development')
            if is_main_process:
                print("Running in DEVELOPMENT environment (default)")

    # Import Django related modules only after settings are configured
    try:
        from django.core.management import execute_from_command_line, ManagementUtility
        
        # Only in main process, not in Django's auto-reloader
        if is_runserver and is_main_process and os.environ.get('RUN_MAIN') is None:
            # 1. Check and create the database if it doesn't exist
            # Use hardcoded values matching development.py
            db_name = 'diivers'
            db_user = 'postgres'
            db_password = 'postgres'
            
            # Try to create database if it doesn't exist
            create_database_if_not_exists(db_name, db_user, db_password)
            
            # 2. Run migrations before starting server
            print("Running migrations before starting server...")
            migrate_utility = ManagementUtility(['manage.py', 'migrate', '--noinput'])
            migrate_utility.execute()
            print("Migrations completed.")
            
            # 3. Check if we should load test data
            load_test_data_flag = os.environ.get('LOAD_TEST_DATA', 'False').lower() in ('true', '1', 't')
            if load_test_data_flag:
                # Load test data before starting server
                print("Loading test data before starting server...")
                load_test_data()
            
        # Now run the actual command (runserver)
        execute_from_command_line(sys.argv)
        
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc


if __name__ == '__main__':
    main()