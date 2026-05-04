"""Per-feature engagement predicates for the wit_bot audit.

Each entry maps a feature to a `is_engaged(user) -> bool` check.

Three predicate kinds:
- 'db'         — query existence in a model written when the user does the thing
- 'event'      — query OnboardingEvent for a frontend-mirrored analytics event
- 'self_report'— treat the user's "Mark as done" tap during walkthrough as proof
                  (also recorded as an OnboardingEvent with prefix 'self_report:')

The audit handler iterates `predicates_for(version)` and bins each into
✓ engaged or ⏳ not yet.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal


PredicateKind = Literal['db', 'event', 'self_report']


@dataclass
class FeaturePredicate:
    feature_key: str
    versions: set[str]
    display_name: str
    description: str
    deep_link: str | None
    kind: PredicateKind
    is_engaged: Callable[[object], bool]  # User -> bool

    def in_version(self, version: str) -> bool:
        return version in self.versions


# ---------- DB-backed predicates ----------

def _has_response(user):
    from qna.models import Response
    return Response.objects.filter(author=user).exists()


def _has_question_send(user):
    from qna.models import ResponseRequest
    return ResponseRequest.objects.filter(requester=user).exists()


def _has_comment(user):
    from comment.models import Comment
    return Comment.objects.filter(author=user).exists()


def _has_private_comment(user):
    from comment.models import Comment
    return Comment.objects.filter(author=user, is_private=True).exists()


def _has_chat_message_to_human(user):
    from chat.models import Message
    from chat.wit_bot import WIT_BOT_USERNAME
    return Message.objects.filter(sender=user).exclude(
        receiver__username=WIT_BOT_USERNAME,
    ).exists()


def _has_mission_post(user):
    from note.models import Note
    return Note.objects.filter(author=user, share_type='mission').exists()


def _has_photo_post(user):
    from note.models import Note
    return Note.objects.filter(author=user, share_type='photo_of_the_day').exists()


def _has_subscription(user):
    from account.models import Subscription
    return Subscription.objects.filter(subscriber=user).exists()


def _has_like(user):
    from like.models import Like
    return Like.objects.filter(user=user).exists()


def _has_reaction(user):
    from reaction.models import Reaction
    return Reaction.objects.filter(user=user).exists()


def _has_checkin_component(component):
    def check(user):
        from check_in.models import CheckInComponentEntry
        return CheckInComponentEntry.objects.filter(
            owner=user, component=component,
        ).exists()
    return check


def _has_pinned_checkin(user):
    from check_in.models import CheckInComponentEntry
    return CheckInComponentEntry.objects.filter(owner=user, is_pinned=True).exists()


def _has_profile_chips(user):
    # Interest M2M is the canonical chips model; CustomChip is per-user;
    # Persona is the legacy M2M. Any of the three counts.
    return (
        user.user_interests.exists()
        or user.user_personas.exists()
        or hasattr(user, 'custom_chips') and user.custom_chips.exists()
    )


def _has_poke(user):
    from check_in.models import Poke
    return Poke.objects.filter(sender=user).exists()


def _is_non_public_account(user):
    return user.is_public is False


def _has_apply_past_posts(user):
    from account.models import Connection
    from django.db.models import Q
    return Connection.objects.filter(
        Q(user1=user, user1_update_past_posts=True)
        | Q(user2=user, user2_update_past_posts=True),
    ).exists()


def _has_browse_mode_pick(user):
    try:
        from browse_mode.models import BrowseModePickEvent
    except ImportError:
        return False
    return BrowseModePickEvent.objects.filter(user=user).exists()


def _has_survey_response(user):
    try:
        from surveys.models import SurveyResponse
    except ImportError:
        return False
    return SurveyResponse.objects.filter(user=user).exists()


def _has_checkin_post(user):
    try:
        from check_in.models import CheckInPost
    except ImportError:
        return False
    return CheckInPost.objects.filter(author=user).exists()


# ---------- Event-backed predicate factory ----------

def _make_event_predicate(event_key: str):
    def check(user):
        from chat.models import OnboardingEvent
        return OnboardingEvent.objects.filter(
            user=user, event_key=event_key,
        ).exists()
    return check


# ---------- Registry ----------

# Goal numbers reference the user's 8-goal scheme from the spec.

PREDICATES: list[FeaturePredicate] = [
    # ---- Goal 1: Cultivate deepening connections ----
    FeaturePredicate(
        feature_key='daily_question_answer',
        versions={'version_w', 'version_q'},
        display_name='Answer a daily question',
        description='Post a response to one of the daily questions.',
        deep_link='/questions',
        kind='db',
        is_engaged=_has_response,
    ),
    FeaturePredicate(
        feature_key='question_send',
        versions={'version_w', 'version_q'},
        display_name='Send a question to a friend',
        description='Pick a question and send it to one of your friends.',
        deep_link='/questions',
        kind='db',
        is_engaged=_has_question_send,
    ),
    FeaturePredicate(
        feature_key='browse_mode',
        versions={'version_w'},
        display_name='Pick a browsing mode',
        description='Quiet vs social — set the vibe for your session. Look for the prompt on the Discover tab (or tap the eye icon in the header).',
        deep_link='/discover',
        kind='db',
        is_engaged=_has_browse_mode_pick,
    ),

    # ---- Goal 3: Scaffold casual relational initiation ----
    FeaturePredicate(
        feature_key='private_comment',
        versions={'version_w'},
        display_name='Post a private comment',
        description="Comment that only the post's author can see.",
        deep_link=None,
        kind='db',
        is_engaged=_has_private_comment,
    ),
    FeaturePredicate(
        feature_key='reaction',
        versions={'version_w'},
        display_name='React with an emoji',
        description='Tap-and-hold on a post or check-in to react.',
        deep_link=None,
        kind='db',
        is_engaged=_has_reaction,
    ),
    FeaturePredicate(
        feature_key='ping_checkin',
        versions={'version_w'},
        display_name="Ping a friend's check-in",
        description='Nudge a friend to update one of their check-in components.',
        deep_link='/friends',
        kind='db',
        is_engaged=_has_poke,
    ),

    # ---- Goal 4: Prevent trust-erosion during repetition ----
    FeaturePredicate(
        feature_key='close_friends_filter',
        versions={'version_w'},
        display_name='Use the Close Friends filter in chat',
        description="In the chat list, look for the 'Close Friends Only' toggle in the header. Flip it on, then off.",
        deep_link='/chats',
        kind='event',
        is_engaged=_make_event_predicate('chat_close_friends_filter_toggled'),
    ),
    FeaturePredicate(
        feature_key='subscribe_bell',
        versions={'version_w', 'version_q'},
        display_name='Tap the subscribe bell on a friend',
        description='Open the bell on a profile or chat to manage subscriptions.',
        deep_link=None,
        kind='db',
        is_engaged=_has_subscription,
    ),

    # ---- Goal 5: Clarity of sharing norms ----
    FeaturePredicate(
        feature_key='mission_of_day',
        versions={'version_w'},
        display_name='Post for Mission of the Day',
        description='Tap the daily mission and submit a post.',
        deep_link='/share',
        kind='db',
        is_engaged=_has_mission_post,
    ),
    FeaturePredicate(
        feature_key='photo_of_day',
        versions={'version_w'},
        display_name='Post a Photo of the Day',
        description='Pick a photo, crop it, write a caption, share.',
        deep_link='/share',
        kind='db',
        is_engaged=_has_photo_post,
    ),
    FeaturePredicate(
        feature_key='checkin_battery',
        versions={'version_w'},
        display_name='Set a social battery check-in',
        description='How social are you feeling? 0–100 with an emoji.',
        deep_link='/update',
        kind='db',
        is_engaged=_has_checkin_component('battery'),
    ),
    FeaturePredicate(
        feature_key='checkin_mood',
        versions={'version_w'},
        display_name='Set a mood check-in',
        description='Up to 5 emojis representing how you feel.',
        deep_link='/update',
        kind='db',
        is_engaged=_has_checkin_component('mood'),
    ),
    FeaturePredicate(
        feature_key='checkin_thought',
        versions={'version_w'},
        display_name='Set a thought check-in',
        description='Up to 88 characters of what is on your mind.',
        deep_link='/update',
        kind='db',
        is_engaged=_has_checkin_component('thought'),
    ),
    FeaturePredicate(
        feature_key='checkin_song',
        versions={'version_w'},
        display_name='Set a song check-in',
        description='Pick a song that captures the moment.',
        deep_link='/update',
        kind='db',
        is_engaged=_has_checkin_component('song'),
    ),

    # ---- Goal 6: Foster sense of community ----
    FeaturePredicate(
        feature_key='daily_survey',
        versions={'version_w', 'version_q'},
        display_name='Complete a survey',
        description="Tap the sidebar → Surveys → fill out what's available.",
        deep_link='/surveys',
        kind='db',
        is_engaged=_has_survey_response,
    ),
    # ---- Goal 7: Support new friendship establishment ----
    # Note: in Ver. W the Discover tab is labelled "Daily Digest" — it's the
    # same route + the same engagement signal, so one predicate covers both.
    FeaturePredicate(
        feature_key='discover_visit',
        versions={'version_w', 'version_q'},
        display_name='Open Discover / Daily Digest',
        description="Browse profile suggestions, mutuals, highlight questions. (Ver. W labels this tab Daily Digest.)",
        deep_link='/discover',
        kind='event',
        is_engaged=_make_event_predicate('discover_opened'),
    ),
    FeaturePredicate(
        feature_key='profile_chips',
        versions={'version_w'},
        display_name='Set profile chips (Persona)',
        description="Pick interests, identities, vibes — they show on your profile.",
        deep_link='/settings',
        kind='db',
        is_engaged=_has_profile_chips,
    ),
    FeaturePredicate(
        feature_key='pinned_checkin',
        versions={'version_w'},
        display_name='Pin a check-in to your profile',
        description="Decorate your profile with a check-in you want to keep visible.",
        deep_link='/update',
        kind='db',
        is_engaged=_has_pinned_checkin,
    ),

    # ---- Goal 8: Safe expansion ----
    FeaturePredicate(
        feature_key='non_public_account',
        versions={'version_q'},
        display_name='Try a non-public account',
        description="Toggle your account to non-public and see what changes. Settings → toggle the public/private switch.",
        deep_link='/settings',
        kind='db',
        is_engaged=_is_non_public_account,
    ),
    FeaturePredicate(
        feature_key='view_as',
        versions={'version_w'},
        display_name='Use "View as…" on your profile',
        description="See how your profile looks to a specific friend or audience. Tap **Take me there** → tap the picker at the top to switch perspectives.",
        deep_link='/my/view-as',
        kind='event',
        is_engaged=_make_event_predicate('view_as_picker_opened'),
    ),
    FeaturePredicate(
        feature_key='apply_privacy_past',
        versions={'version_w'},
        display_name='Apply privacy change to past posts',
        description="When you upgrade a friend to close-friend, also apply the new visibility to past posts.",
        deep_link='/friends',
        kind='db',
        is_engaged=_has_apply_past_posts,
    ),

    # ---- Q-only ----
    FeaturePredicate(
        feature_key='checkin_post',
        versions={'version_q'},
        display_name='Post an image+text check-in',
        description='Q-style check-in — image with a caption, lives in the stories rail.',
        deep_link='/share',
        kind='db',
        is_engaged=_has_checkin_post,
    ),
    FeaturePredicate(
        feature_key='stories_scroll',
        versions={'version_q'},
        display_name='Scroll the check-in stories',
        description="Horizontal rail of friends' image+text check-ins on top of the feed.",
        deep_link='/feed',
        kind='event',
        is_engaged=_make_event_predicate('checkin_stories_scrolled'),
    ),
    FeaturePredicate(
        feature_key='q_feed_visit',
        versions={'version_q'},
        display_name='Open the Friends feed',
        description="Q's main feed — vertical scroll through friends' posts.",
        deep_link='/feed',
        kind='event',
        is_engaged=_make_event_predicate('q_feed_opened'),
    ),
    FeaturePredicate(
        feature_key='my_tab_visit',
        versions={'version_q'},
        display_name='Open the My tab',
        description="Q's profile tab in the bottom nav.",
        deep_link='/my',
        kind='event',
        is_engaged=_make_event_predicate('my_tab_opened'),
    ),
]


def predicates_for(version: str) -> list[FeaturePredicate]:
    """Return predicates applicable to the given version."""
    return [p for p in PREDICATES if p.in_version(version)]


def predicate_by_key(feature_key: str) -> FeaturePredicate | None:
    for p in PREDICATES:
        if p.feature_key == feature_key:
            return p
    return None
