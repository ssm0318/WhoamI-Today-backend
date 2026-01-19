import os
import sys
import django
import getpass
from django.conf import settings

# Add current working directory to sys.path to find project modules
sys.path.append(os.getcwd())

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'adoorback.settings.base')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

def create_superuser():
    username = 'admin'
    email = 'whoami.today.official@gmail.com'
    
    print(f"Creating superuser with:")
    print(f"Username: {username}")
    print(f"Email: {email}")
    
    # Check if user already exists
    if User.objects.filter(email=email).exists():
        print(f"User with email {email} already exists.")
        return

    if User.objects.filter(username=username).exists():
        print(f"User with username {username} already exists.")
        return

    try:
        password = getpass.getpass("Enter password for superuser: ")
        confirm_password = getpass.getpass("Confirm password: ")

        if password != confirm_password:
            print("Error: Passwords do not match.")
            return

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )
        print("Superuser created successfully.")

    except KeyboardInterrupt:
        print("\nOperation cancelled.")
    except Exception as e:
        print(f"Error creating superuser: {e}")

if __name__ == '__main__':
    create_superuser()
