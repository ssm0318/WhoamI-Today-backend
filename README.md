# WhoAmI-Today Backend

## 🌐 Overview

WhoAmI-Today Backend is a Django REST API application that powers an innovative social platform for users to discover and express themselves through interactive experiences. Built with modern backend technologies, it provides robust APIs for authentication, daily check-ins, notes, and social interactions for both web and mobile applications.

## 🛠 Tech Stack

- **Framework**: Django 4.2.14
- **Language**: Python 3.9+
- **Database**: PostgreSQL 13
- **Cache**: Redis + Django Cache Framework
- **Real-time**: Django Channels 4.0.0 with Redis
- **Authentication**: Django REST Framework + JWT (djangorestframework-simplejwt 5.2.0)
- **Push Notifications**: Firebase Cloud Messaging (fcm-django 2.2.1)
- **Translation**: Google Cloud Translate API 2.0.1 + django-modeltranslation 0.18.7
- **File Storage**: Django File Storage (configurable)
- **Task Scheduling**: django-cron 0.5.1
- **API Documentation**: Django REST Framework
- **Error Tracking**: Sentry SDK 0.19.4
- **Code Quality**: Pylint, Coverage, Django Test Framework

## 🚀 Getting Started

### Prerequisites

Make sure you have the following tools installed:

- **Python**: 3.9.0 or later
- **PostgreSQL**: 13 or later
- **Redis**: Latest stable version
- **Gettext**: For internationalization

### Environment Setup

#### Set Environment Variables

- **Python**: Set environment variables such as `SECRET_KEY`, `DB_PASSWORD`, `EMAIL_HOST_PASSWORD` inside `.zshrc`, `.bashrc`, or `.bash_profile`
- **FCM**: Place Firebase service account key at `backend/adoorback/adoorback/serviceAccountKey.json`

#### Docker Development

The project supports containerized development with Docker Compose:

```bash
# Development environment
docker-compose -f docker-compose.development.yml up

# Production environment
docker-compose -f docker-compose.production.yml up
```

### Installation

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd WhoAmI-Today-backend
   ```

2. **Install system dependencies**

   ```bash
   # macOS
   brew install gettext redis postgresql
   brew services start redis
   brew services start postgresql
   ```

3. **Install Python dependencies**

   ```bash
   cd adoorback
   pip install -r requirements.txt
   ```

4. **Database Migration and Seeding**

   ```bash
   python manage.py migrate

   # Seed test data
   python manage.py shell
   from adoorback.test.seed import set_seed
   set_seed(20)
   exit()
   ```

5. **Run Server**

   ```bash
   python manage.py runserver
   ```

   The API server will start on `http://localhost:8000` with auto-reload enabled.

## 🗄️ Database Configuration

### Local PostgreSQL Setup

#### 1. Update development.py Database Configuration

Update your `development.py` file DATABASES settings:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'whoami_today',  # Change to desired database name
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'HOST': 'localhost',
        'POST': '',
    },
}
```

#### 2. Install PostgreSQL on macOS

```bash
# Install PostgreSQL
brew install postgresql

# Start PostgreSQL service (needs to be run after PC restart)
brew services start postgresql

# Verify installation by checking PostgreSQL version
psql -V
```

#### 3. Configure PostgreSQL Database

```bash
# Connect to PostgreSQL
psql -U postgres
# or
psql postgres

# Check user list
\du

# If postgres user doesn't exist, create it
create user postgres with password 'postgres';

# If postgres user exists, change password
alter user postgres with password 'postgres';

# Create database (semicolon is required)
create database whoami_today;

# Check if the database is in the database list
\l

# Configure postgres user settings and grant permissions
alter role postgres set client_encoding to 'utf-8';
alter role postgres set timezone to 'America/Los_Angeles';
grant all privileges on database whoami_today to postgres;

# Exit PostgreSQL connection
\q
```

#### 4. Install Python Dependencies

```bash
# Install psycopg2 in your virtual environment
pip install psycopg2
```

#### 5. Run Database Migration

```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Verify server runs correctly
python manage.py runserver
```

### Drop PostgreSQL Database

If you need to reset the database:

```bash
psql -U postgres
drop database whoami_today;
create database whoami_today with owner postgres;
alter role postgres set client_encoding to 'utf-8';
alter role postgres set timezone to 'America/Los_Angeles';
grant all privileges on database whoami_today to postgres;
\q

# Need to migrate again
cd adoorback
python manage.py migrate
```

## 🧪 Testing

### Running Tests and Coverage

```bash
# Linting
pylint **/*.py --load-plugins pylint_django

# Database migrations for testing
python manage.py makemigrations account feed comment like notification user_report content_report
python manage.py migrate

# Run tests with coverage
coverage run --source='.' --omit='*/migrations/*','adoorback/*','feed/algorithms/*','feed/cron.py','account/cron.py','locustfile.py','manage.py','*/wsgi.py','*/asgi.py','*/utils/*' ./manage.py test
coverage run --source='.' --branch --omit='*/migrations/*','adoorback/*','feed/algorithms/*','feed/cron.py','account/cron.py','locustfile.py','manage.py','*/wsgi.py','*/asgi.py','*/utils/*' ./manage.py test

# Generate coverage report
coverage report -m

# Test only specific model [model_name]
coverage run --source='.' --omit='*/migrations/*','adoorback/*','feed/algorithms/*','feed/cron.py','account/cron.py','locustfile.py','manage.py','*/wsgi.py','*/asgi.py','*/utils/*' ./manage.py test [model_name]
coverage run --source='.' --branch --omit='*/migrations/*','adoorback/*','feed/algorithms/*','feed/cron.py','account/cron.py','locustfile.py','manage.py','*/wsgi.py','*/asgi.py','*/utils/*' ./manage.py test [model_name]
coverage report -m
```

### Test Coverage

The project maintains comprehensive test coverage excluding:

- Migration files
- Third-party utilities
- Configuration files
- Algorithm files
- Cron job scripts

## 📁 Project Structure

```
adoorback/
├── account/            # User authentication and profiles
├── qna/               # Questions and responses system
├── check_in/          # Daily check-in functionality
├── note/              # Personal notes and journaling
├── notification/      # Push notifications and alerts
├── like/              # Social interactions (likes)
├── comment/           # Comments system
├── ping/              # Ping/poke functionality
├── reaction/          # Reaction system for content
├── user_report/       # User reporting and moderation
├── content_report/    # Content reporting system
├── translate/         # Translation services
├── custom_fcm/        # Firebase Cloud Messaging
├── tracking/          # User activity tracking
├── utils/             # Shared utilities and helpers
├── adoorback/         # Core Django settings and configuration
│   ├── settings/      # Environment-specific settings
│   ├── utils/         # Core utilities
│   ├── management/    # Custom Django commands
│   └── assets/        # Static assets and data files
└── manage.py          # Django management script
```

## 🔧 Key Features

### Core Functionality

- **User Management**: Registration, authentication, profile management
- **Social Platform**: Friend system, user interactions, social feeds
- **Daily Check-ins**: Emotional and activity tracking with calendar integration
- **Q&A System**: Daily questions, personalized responses, and discovery
- **Notes & Journaling**: Personal note-taking with image support
- **Push Notifications**: Firebase integration for real-time alerts

### Advanced Features

- **Multi-language Support**: Korean/English with Google Translate integration
- **Content Moderation**: Automated and manual content reporting system
- **Analytics & Tracking**: Comprehensive user behavior tracking
- **Cron Jobs**: Automated daily tasks and notifications
- **Content Management**: Admin interface for content moderation
- **File Upload**: Secure image and file handling
- **API Rate Limiting**: Built-in request throttling

## 🚀 Manual Backend Deployment

### A. Server Access

1. Download the PEM key and place it in an appropriate location (e.g., `Documents` folder), then set permissions with `chmod 400 {key_name}.pem`. (The PEM key should not be public, so we remove all permissions except read access)
2. From the directory containing the PEM key, enter `ssh -i {key_name}.pem ubuntu@{server_ip}` to access the server. (For first-time access, you need to enter `yes`)

### B. Accessing Backend Code

1. Enter `source ~/venv3.9/bin/activate` to activate the Python virtual environment.

   You should see `(venv3.9)` appear to the left of `ubuntu@ip-172-31-19-133` if successful.

2. From the home directory, enter `cd WhoAmI-Today-backend` to navigate to where the backend code is located.

### C. Updating Code

1. Confirm that the git branch is set to `main`, then run `git pull` to update the code.
   1. username: Your GitHub username
   2. password: Your GitHub token
2. (If there are changes to the backend DB structure) Navigate to `~/WhoAmI-Today-backend/adoorback` with `cd adoorback` command, then enter the following commands in order:

   ```python
   (If new packages are installed) pip install -r requirements.txt
   ./manage.py migrate
   ```

3. (If translation fields are added to existing backend models) Navigate to `~/WhoAmI-Today-backend/adoorback` with `cd adoorback` command, then enter the following:

   ```bash
   ./manage.py update_translation_fields
   ```

4. (If there are changes to backend code) Enter `sudo systemctl restart uwsgi`.

## 🛠️ Server Management Commands

1. **View backend logs in real-time**: `tail -f /var/log/uwsgi/WhoAmI-Today-backend.log`
2. **Check nginx status**: `sudo systemctl status nginx`
3. **Restart database**: `sudo systemctl restart postgresql.service`

## 🔐 Security & Configuration

### Environment Variables

All sensitive configuration is managed through environment variables:

- Database credentials
- API keys (Firebase, Google Translate, Anthropic)
- JWT secrets
- Email configuration

#### `ANTHROPIC_API_KEY`

Required for AI-generated TMI placeholders on the Share page. Set this in your shell profile or `.env.development`:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Without this key the `/api/user/tmi-placeholder/` endpoint falls back to a curated list of static examples.

### Security Features

- JWT-based authentication with refresh tokens
- CORS configuration for frontend integration
- Request filtering and validation
- Content sanitization
- Rate limiting and throttling
- Secure file upload validation

### Protected Files (in .gitignore)

- `serviceAccountKey.json` - Firebase configuration
- `coherent-flame-*.json` - Google Cloud credentials
- `.env*` - Environment variable files
- Database dumps and user data files
- Log files and cache data

## 🗄️ Database Schema

The application uses PostgreSQL with the following main models:

- **User**: Extended Django user model with social features
- **Question/Response**: Q&A system with algorithmic matching
- **Note**: Personal journaling with multimedia support
- **CheckIn**: Daily emotional and activity tracking
- **Notification**: Push notification management
- **Like/Comment/Reaction**: Social interaction models

## 🔄 Cron Jobs

Automated daily tasks:

- `DailyQuestionCronJob`: Generate and distribute daily questions
- `SendDailyWhoAmINotiCronJob`: Send daily check-in reminders
- `AutoCloseSessionsCronJob`: Clean up expired sessions
- `SendDailySurveyNotiCronJob`: Send survey notifications

## 🌍 Internationalization

- **Languages**: Korean (ko) and English (en)
- **Translation Management**: django-modeltranslation
- **Google Translate Integration**: Automatic content translation
- **Localized Content**: Questions, notifications, and UI text

## 📊 Monitoring & Maintenance

- **Health Check Endpoint**: `/api/health/` for monitoring
- **Admin Interface**: `/api/secret/` for content management
- **Automated Backups**: Database backup scripts in `cron/`
- **Log Management**: Structured logging with rotation
- **Performance Monitoring**: Built-in Django tracking

## 📧 Contact

For questions, contributions, or support:

- **Email**: [whoami.today.official@gmail.com](mailto:whoami.today.official@gmail.com)
- **Team**: Team WhoAmI

---

## 🚨 Important Notes

- Ensure all environment variables are properly configured before deployment
- Firebase service account key must be properly secured and configured
- Database migrations should be tested in development before production deployment
- Regular security updates and dependency management are recommended
