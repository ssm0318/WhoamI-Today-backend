# URL name -> action mapping for experiment logging.
#
# Each entry maps a Django URL name to an action category and name.
# For URLs that handle multiple HTTP methods with different semantics,
# use 'name_by_method' instead of 'name'.

ROUTE_ACTION_MAP = {
    # ===== Session / Auth =====
    'login':                            {'category': 'session_auth', 'name': 'login'},
    'logout':                           {'category': 'session_auth', 'name': 'logout'},
    'user-email-check':                 {'category': 'session_auth', 'name': 'email_check'},
    'user-password-check':              {'category': 'session_auth', 'name': 'password_check'},
    'user-username-check':              {'category': 'session_auth', 'name': 'username_check'},
    'user-birthdate-check':             {'category': 'session_auth', 'name': 'birthdate_check'},
    'user-inviter-birthdate-check':     {'category': 'session_auth', 'name': 'inviter_birthdate_check'},
    'user-signup':                      {'category': 'session_auth', 'name': 'signup'},
    'user-verify-email':                {'category': 'session_auth', 'name': 'verify_email'},
    'user-send-reset-password-email':   {'category': 'session_auth', 'name': 'send_reset_password_email'},
    'user-reset-password':              {'category': 'session_auth', 'name': 'reset_password'},
    'current-user-reset-password':      {'category': 'session_auth', 'name': 'current_user_reset_password'},
    'user-password-confirm':            {'category': 'session_auth', 'name': 'password_confirm'},
    'start_session':                    {'category': 'session_auth', 'name': 'session_start'},
    'end_session':                      {'category': 'session_auth', 'name': 'session_end'},
    'touch_session':                    {'category': 'session_auth', 'name': 'session_touch'},

    # ===== Current User / Profile =====
    'current-user-detail':              {'category': 'profile_management', 'name_by_method': {
                                            'GET': 'current_user_detail_view',
                                            'PUT': 'current_user_detail_update',
                                        }},
    'current-user-delete':              {'category': 'profile_management', 'name': 'account_delete'},
    'current-user-profile':             {'category': 'profile_management', 'name_by_method': {
                                            'GET': 'current_user_profile_view',
                                            'PUT': 'current_user_profile_update',
                                        }},
    'current-user-note-list':           {'category': 'content_consumption', 'name': 'current_user_note_list'},
    'current-user-response-list':       {'category': 'content_consumption', 'name': 'current_user_response_list'},
    'received-response-request-list':   {'category': 'content_consumption', 'name': 'received_response_request_list'},
    'current-user-friend-search':       {'category': 'discovery_feed', 'name': 'current_user_friend_search'},
    'current-user-all-post-list':       {'category': 'content_consumption', 'name': 'current_user_all_post_list'},
    'current-user-latest-visibility':   {'category': 'profile_management', 'name_by_method': {
                                            'GET': 'latest_visibility_view',
                                            'PUT': 'latest_visibility_update',
                                        }},
    'current-user-note-status':         {'category': 'content_consumption', 'name': 'current_user_note_status'},
    'current-user-interest-update':     {'category': 'profile_management', 'name': 'interest_update'},
    'current-user-persona-update':      {'category': 'profile_management', 'name': 'persona_update'},
    'current-user-chips-update':        {'category': 'profile_management', 'name': 'chips_update'},
    'custom-chip-list-create':          {'category': 'profile_management', 'name_by_method': {
                                            'GET': 'custom_chip_list',
                                            'POST': 'custom_chip_create',
                                        }},
    'chip-categories':                  {'category': 'profile_management', 'name': 'chip_categories_view'},

    # ===== Interest / Persona Search & Recommendation =====
    'interest-search':                  {'category': 'discovery_feed', 'name': 'interest_search'},
    'persona-search':                   {'category': 'discovery_feed', 'name': 'persona_search'},
    'interest-recommendation':          {'category': 'discovery_feed', 'name': 'interest_recommendation'},
    'persona-recommendation':           {'category': 'discovery_feed', 'name': 'persona_recommendation'},

    # ===== User Profile (other users) =====
    'user-search':                      {'category': 'discovery_feed', 'name': 'user_search'},
    'user-detail':                      {'category': 'discovery_feed', 'name': 'user_profile_view'},
    'user-note-list':                   {'category': 'content_consumption', 'name': 'user_note_list'},
    'user-response-list':               {'category': 'content_consumption', 'name': 'user_response_list'},
    'friend-friend-list':               {'category': 'discovery_feed', 'name': 'friend_friend_list'},
    'user-all-post-list':               {'category': 'content_consumption', 'name': 'user_all_post_list'},
    'user-unread-post-list':            {'category': 'content_consumption', 'name': 'user_unread_post_list'},
    'user-mark-all-notes-as-read':      {'category': 'content_consumption', 'name': 'mark_all_notes_read'},
    'user-mark-all-responses-as-read':  {'category': 'content_consumption', 'name': 'mark_all_responses_read'},

    # ===== Friends =====
    'friend-list':                      {'category': 'relationship_change', 'name_by_method': {
                                            'GET': 'friend_list_view',
                                            'POST': 'friend_request_send',
                                        }},
    'friend-update-list':               {'category': 'discovery_feed', 'name': 'friend_update_list'},
    'current-user-friends-update':      {'category': 'relationship_change', 'name': 'friend_list_update'},
    'user-favorite-add':                {'category': 'relationship_change', 'name': 'favorite_add'},
    'user-favorite-destroy':            {'category': 'relationship_change', 'name': 'favorite_remove'},
    'user-hidden-add':                  {'category': 'relationship_change', 'name': 'hidden_add'},
    'user-hidden-destroy':              {'category': 'relationship_change', 'name': 'hidden_remove'},
    'connection-choice-update':         {'category': 'relationship_change', 'name': 'connection_update'},
    'user-friend-destroy':              {'category': 'relationship_change', 'name': 'unfriend'},

    # ===== Feed =====
    'friend-feed':                      {'category': 'discovery_feed', 'name': 'friend_feed_view'},
    'full-friend-feed':                 {'category': 'discovery_feed', 'name': 'full_friend_feed_view'},
    'discover-feed':                    {'category': 'discovery_feed', 'name': 'discover_feed_view'},

    # ===== Friend Requests =====
    'user-friend-request-list':         {'category': 'relationship_change', 'name_by_method': {
                                            'GET': 'friend_request_list',
                                            'POST': 'friend_request_send',
                                        }},
    'user-sent-friend-request-list':    {'category': 'relationship_change', 'name': 'sent_friend_request_list'},
    'user-friend-request-destroy':      {'category': 'relationship_change', 'name': 'friend_request_cancel'},
    'user-friend-request-update':       {'category': 'relationship_change', 'name': 'friend_request_respond'},

    # ===== Friend Recommendations =====
    'user-recommended-friends-list':    {'category': 'discovery_feed', 'name': 'recommended_friends_list'},
    'block-rec-create':                 {'category': 'moderation', 'name': 'block_recommendation'},

    # ===== Subscriptions =====
    'subscribe-user-content':           {'category': 'subscription', 'name': 'subscribe'},
    'unsubscribe-user-content':         {'category': 'subscription', 'name': 'unsubscribe'},

    # ===== TMI =====
    'tmi-placeholder':                  {'category': 'content_consumption', 'name': 'tmi_placeholder'},

    # ===== QnA =====
    # NOTE: 'response-list' name is shared with reaction/urls.py. Disambiguated by PATH_PREFIX_MAP.
    'response-detail':                  {'category': 'content_creation', 'name_by_method': {
                                            'GET': 'response_detail_view',
                                            'PUT': 'response_edit',
                                            'PATCH': 'response_edit',
                                            'DELETE': 'response_delete',
                                        }},
    'response-comments':                {'category': 'content_consumption', 'name': 'response_comments_view'},
    'response-interaction-user-list':   {'category': 'content_consumption', 'name': 'response_interactions_view'},
    'response-read':                    {'category': 'content_consumption', 'name': 'response_read'},
    'daily-question-list':              {'category': 'content_consumption', 'name': 'daily_question_list'},
    'question-list':                    {'category': 'content_consumption', 'name': 'question_list'},
    'question-detail':                  {'category': 'content_consumption', 'name': 'question_detail_view'},
    'response-request-create':          {'category': 'social_interaction', 'name': 'response_request_create'},

    # ===== Notes =====
    'note-list':                        {'category': 'content_creation', 'name_by_method': {
                                            'GET': 'note_list',
                                            'POST': 'note_create',
                                        }},
    'note-detail':                      {'category': 'content_creation', 'name_by_method': {
                                            'GET': 'note_detail_view',
                                            'PUT': 'note_edit',
                                            'PATCH': 'note_edit',
                                            'DELETE': 'note_delete',
                                        }},
    'note-comments':                    {'category': 'content_consumption', 'name': 'note_comments_view'},
    'note-interaction-user-list':       {'category': 'content_consumption', 'name': 'note_interactions_view'},
    'note-read':                        {'category': 'content_consumption', 'name': 'note_read'},

    # ===== Notices =====
    'notice-list':                      {'category': 'content_consumption', 'name': 'notice_list'},
    'notice-detail':                    {'category': 'content_consumption', 'name': 'notice_detail_view'},
    'notice-comments':                  {'category': 'content_consumption', 'name': 'notice_comments_view'},
    'notice-interaction-user-list':     {'category': 'content_consumption', 'name': 'notice_interactions_view'},
    'user-mark-all-notices-as-read':    {'category': 'content_consumption', 'name': 'mark_all_notices_read'},

    # ===== Check-In =====
    'current-check-in':                 {'category': 'content_creation', 'name_by_method': {
                                            'GET': 'check_in_view',
                                            'POST': 'check_in_create',
                                        }},
    'check-in-detail':                  {'category': 'content_consumption', 'name': 'check_in_detail_view'},
    'check-in-read':                    {'category': 'content_consumption', 'name': 'check_in_read'},
    'current-user-latest-check-in-visibility': {'category': 'profile_management', 'name_by_method': {
                                            'GET': 'check_in_visibility_view',
                                            'PUT': 'check_in_visibility_update',
                                        }},
    'latest-check-in':                  {'category': 'content_consumption', 'name': 'latest_check_in_view'},
    'current-song':                     {'category': 'content_creation', 'name_by_method': {
                                            'GET': 'song_view',
                                            'POST': 'song_create',
                                        }},
    'my-song-detail':                   {'category': 'content_consumption', 'name': 'song_detail_view'},
    'check-in-react':                   {'category': 'social_interaction', 'name': 'check_in_reaction_toggle'},
    'check-in-reactions':               {'category': 'content_consumption', 'name': 'check_in_reactions_view'},
    'poke-create':                      {'category': 'social_interaction', 'name': 'poke_create'},
    'poke-sent':                        {'category': 'social_interaction', 'name': 'poke_sent_list'},
    'poke-delete':                      {'category': 'social_interaction', 'name': 'poke_delete'},

    # ===== Comments =====
    'comment-create':                   {'category': 'social_interaction', 'name': 'comment_create'},
    'comment-detail':                   {'category': 'social_interaction', 'name_by_method': {
                                            'GET': 'comment_detail_view',
                                            'PUT': 'comment_edit',
                                            'PATCH': 'comment_edit',
                                            'DELETE': 'comment_delete',
                                        }},
    'comment-like-user-list':           {'category': 'content_consumption', 'name': 'comment_like_user_list'},

    # ===== Likes =====
    'like-list':                        {'category': 'social_interaction', 'name_by_method': {
                                            'GET': 'like_list',
                                            'POST': 'like_create',
                                        }},
    'like-destroy':                     {'category': 'social_interaction', 'name': 'like_delete'},

    # ===== Reactions (URL name 'response-list' conflicts with qna) =====
    # Handled via PATH_PREFIX_MAP below
    'reaction-destroy':                 {'category': 'social_interaction', 'name': 'reaction_delete'},

    # ===== Ping (messaging) =====
    'ping-room-list':                   {'category': 'messaging', 'name': 'ping_room_list'},
    'ping_list':                        {'category': 'messaging', 'name': 'ping_list'},
    'ping-request-create':              {'category': 'messaging', 'name': 'ping_request_create'},
    'ping-request-sent-list':           {'category': 'messaging', 'name': 'ping_request_sent_list'},
    'ping-request-update':              {'category': 'messaging', 'name': 'ping_request_respond'},

    # ===== Chat =====
    # Most chat URLs have no name; handled via PATH_PREFIX_MAP
    'message-like-list':                {'category': 'messaging', 'name': 'message_like_list'},

    # ===== Notifications =====
    'notification-list':                {'category': 'notification', 'name': 'notification_list'},
    'friend-request-noti-list':         {'category': 'notification', 'name': 'friend_request_noti_list'},
    'response-request-noti-list':       {'category': 'notification', 'name': 'response_request_noti_list'},
    'notification-read':                {'category': 'notification', 'name': 'notification_read'},
    'mark-all-notifications-read':      {'category': 'notification', 'name': 'mark_all_notifications_read'},

    # ===== Content/User Reports =====
    'content-report-list':              {'category': 'moderation', 'name_by_method': {
                                            'GET': 'content_report_list',
                                            'POST': 'content_report_create',
                                        }},
    'user-report-list':                 {'category': 'moderation', 'name_by_method': {
                                            'GET': 'user_report_list',
                                            'POST': 'user_report_create',
                                        }},

    # ===== Playlist =====
    'playlist-feed':                    {'category': 'discovery_feed', 'name': 'playlist_feed_view'},

    # ===== Tracking =====
    'tracking-dashboard':               {'category': 'other', 'name': 'tracking_dashboard'},

    # ===== Version Q Endpoints =====
    'q-current-user-detail':            {'category': 'profile_management', 'name_by_method': {
                                            'GET': 'current_user_detail_view',
                                            'PUT': 'current_user_detail_update',
                                        }},
    'q-current-user-note-list':         {'category': 'content_consumption', 'name': 'current_user_note_list'},
    'q-current-user-all-post-list':     {'category': 'content_consumption', 'name': 'current_user_all_post_list'},
    'q-user-detail':                    {'category': 'discovery_feed', 'name': 'user_profile_view'},
    'q-user-note-list':                 {'category': 'content_consumption', 'name': 'user_note_list'},
    'q-user-all-post-list':             {'category': 'content_consumption', 'name': 'user_all_post_list'},
    'q-friend-feed':                    {'category': 'discovery_feed', 'name': 'friend_feed_view'},
    'q-note-create':                    {'category': 'content_creation', 'name_by_method': {
                                            'GET': 'note_list',
                                            'POST': 'note_create',
                                        }},
    'q-note-detail':                    {'category': 'content_creation', 'name_by_method': {
                                            'GET': 'note_detail_view',
                                            'PUT': 'note_edit',
                                            'PATCH': 'note_edit',
                                            'DELETE': 'note_delete',
                                        }},
    'q-response-create':                {'category': 'content_creation', 'name_by_method': {
                                            'GET': 'response_list',
                                            'POST': 'response_create',
                                        }},
    'q-response-detail':                {'category': 'content_creation', 'name_by_method': {
                                            'GET': 'response_detail_view',
                                            'PUT': 'response_edit',
                                            'PATCH': 'response_edit',
                                            'DELETE': 'response_delete',
                                        }},
}


# Path-prefix based fallback for URLs without names or with conflicting names.
# Checked in order; first match wins.
# 'name_by_method' is supported here too.
PATH_PREFIX_MAP = [
    # Disambiguate 'response-list' conflict: reaction vs qna
    {
        'prefix': '/api/reactions/',
        'category': 'social_interaction',
        'name_by_method': {
            'GET': 'reaction_list',
            'POST': 'reaction_create',
        },
    },
    {
        'prefix': '/api/qna/responses/',
        'url_name': 'response-list',
        'category': 'content_creation',
        'name_by_method': {
            'GET': 'response_list',
            'POST': 'response_create',
        },
    },

    # Chat URLs (most have no name)
    {
        'prefix': '/api/chat/rooms/search/',
        'category': 'messaging',
        'name': 'chat_message_search',
    },
    {
        'prefix': '/api/chat/rooms/one_on_one/',
        'category': 'messaging',
        'name': 'one_on_one_chat_room_view',
    },
    {
        'prefix': '/api/chat/rooms/friend/',
        'category': 'messaging',
        'name': 'chat_room_friend_list',
    },
    {
        'prefix': '/api/chat/rooms/',
        'category': 'messaging',
        'name_by_method': {
            'GET': 'chat_room_list',
            'POST': 'chat_room_create',
            'PUT': 'chat_room_update',
            'DELETE': 'chat_room_delete',
        },
    },
    {
        'prefix': '/api/chat/messages/likes/',
        'category': 'messaging',
        'name': 'message_like_list',
    },
    {
        'prefix': '/api/chat/',
        'category': 'messaging',
        'name': 'chat_messages_list',
    },

    # Translate (no URL name)
    {
        'prefix': '/api/translate/',
        'category': 'other',
        'name': 'translate',
    },

    # FCM devices (skip from experiment logging)
    {
        'prefix': '/api/devices/',
        'skip': True,
    },
]
