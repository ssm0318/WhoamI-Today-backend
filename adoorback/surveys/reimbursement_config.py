POINTS_PER_DOLLAR = 10

WIT_BOT_AUDIT_PARTIAL_POINTS = 10
WIT_BOT_AUDIT_PHASE_1_MAX_POINTS = 50
WIT_BOT_AUDIT_PHASE_2_MAX_POINTS = 50
APP_USAGE_PHASE_1_FULL_POINTS = 50
APP_USAGE_PHASE_2_FULL_POINTS = 50
APP_USAGE_PHASE_PARTIAL_POINTS = 20
INTERVIEW_COMPLETED_POINTS = 200
INTERVIEW_REBECCA_POINTS = 200
INTERVIEW_SIGNUP_MAX_POINTS = INTERVIEW_COMPLETED_POINTS
INTERVIEW_DOLLAR_CENTS = 2000
INTERVIEW_SIGNUP_URL = 'https://calendly.com/jaewonkim/60min'
INTERVIEW_SIGNUP_DEADLINE = '2026-08-31'
DROPOUT_SURVEY_URL = 'https://jaewonkim.me/whoami-dropout/'
DROPOUT_SURVEY_POINTS = 50
DROPOUT_SURVEY_DOLLAR_CENTS = 500
FRIEND_INVITE_POINTS_PER_FRIEND = 100
FRIEND_INVITE_MAX_POINTS = 500

WIT_BOT_AUDIT_PHASES = {
    1: {
        'source_slug': 'wit_bot_audit_phase_1',
        'title_en': 'WIT bot and boss quiz - Phase 1',
        'title_ko': 'WIT 봇 및 보스 퀴즈 - 1단계',
        'max_points': WIT_BOT_AUDIT_PHASE_1_MAX_POINTS,
    },
    2: {
        'source_slug': 'wit_bot_audit_phase_2',
        'title_en': 'WIT bot and boss quiz - Phase 2',
        'title_ko': 'WIT 봇 및 보스 퀴즈 - 2단계',
        'max_points': WIT_BOT_AUDIT_PHASE_2_MAX_POINTS,
    },
}

APP_USAGE_PHASES = {
    1: {
        'source_slug': 'app_usage_phase_1',
        'title_en': 'App usage - Phase 1',
        'title_ko': 'App usage - Phase 1',
        'max_points': APP_USAGE_PHASE_1_FULL_POINTS,
    },
    2: {
        'source_slug': 'app_usage_phase_2',
        'title_en': 'App usage - Phase 2',
        'title_ko': 'App usage - Phase 2',
        'max_points': APP_USAGE_PHASE_2_FULL_POINTS,
    },
}
