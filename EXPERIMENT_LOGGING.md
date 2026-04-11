# Experiment API Logging System

## Problem

Existing logs (`error.log`, `info.log`, `debug.log`) are text-based, mixed with Django debug output, and lack experiment context (version, group). Not suitable for behavior analysis across the 4-week Q/W field deployment.

## Solution

A dedicated `experiment.log` file in JSONL format (one JSON object per line), completely separated from dev logs. Every API request is automatically captured via middleware — no view code changes needed.

## Created Files

| File | Purpose |
|---|---|
| `adoorback/adoorback/experiment_logging/__init__.py` | Package init |
| `adoorback/adoorback/experiment_logging/route_map.py` | Maps ~90 URL names to action categories and names |
| `adoorback/adoorback/experiment_logging/formatters.py` | JSON log formatter |
| `adoorback/adoorback/experiment_logging/middleware.py` | Core middleware that intercepts all API requests |

## Modified Files

`adoorback/adoorback/settings/base.py`:
- Added `ExperimentLoggingMiddleware` at the end of `MIDDLEWARE` (after `AuthenticationMiddleware` so `request.user` is available)
- Added `experiment_json` formatter, `experiment_file` handler, and `experiment` logger to `LOGGING` with `propagate: False` to keep it isolated from dev logs

## Log Format

Each line in `experiment.log`:

```json
{
  "timestamp": "2026-04-15T14:23:01.456+09:00",
  "request_id": "a1b2c3d4e5f6",
  "duration_ms": 42,
  "user": {
    "id": 17,
    "username": "alice",
    "current_ver": "version_w",
    "user_group": "group_w_first",
    "user_type": "direct"
  },
  "request": {
    "method": "POST",
    "path": "/api/likes/",
    "body": {"target_type": "note", "target_id": 42}
  },
  "response": {"status_code": 201},
  "action": {
    "category": "social_interaction",
    "name": "like_create",
    "target_id": 42,
    "target_type": "note"
  },
  "client": {"os": "iOS", "page": "friend_feed"},
  "api_version": "w"
}
```

## Action Categories (11 total)

| Category | Actions |
|---|---|
| `content_creation` | note/response/check_in/song create, edit, delete |
| `social_interaction` | like, comment, reaction, poke, response_request |
| `relationship_change` | friend_request, connection_update, unfriend, favorite, hidden |
| `messaging` | ping, ping_request, chat rooms/messages |
| `discovery_feed` | feed, discover, search, profile views |
| `content_consumption` | read marking, detail/comments/interactions views |
| `session_auth` | login, logout, signup, app_session start/end/touch |
| `subscription` | subscribe, unsubscribe |
| `moderation` | content_report, user_report, block_recommendation |
| `profile_management` | profile/interest/persona/chip updates |
| `notification` | notification list, read, mark_all_read |

## Key Design Decisions

- **Middleware-only approach** — no per-view changes required. Action classification is done via a static URL name-to-action map (`route_map.py`)
- **PATH_PREFIX_MAP** handles unnamed URLs (chat endpoints) and disambiguates the `response-list` name conflict between `reaction/urls.py` and `qna/urls.py`
- **Full request body stored** for POST/PUT/PATCH (note content, comments, etc.). Only `password`, `token`, `secret`, `registration_id` are filtered out
- **Skipped paths**: `/api/health/`, `/api/secret/`, `/api/devices/`, `/static/`, `/media/`
- **Superuser requests** are logged with `user_type: "admin"` (filterable later)
- **Daily log rotation** at midnight, consistent with existing log setup
- **Existing Docker volume mount** (`./adoorback/adoorback/logs:/app/adoorback/adoorback/logs`) already covers the new log file

## Verification

```bash
# After running the server and making API calls:
cat logs/experiment.log | jq .
# or
cat logs/experiment.log | python -m json.tool
```
