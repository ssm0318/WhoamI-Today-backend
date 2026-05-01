from django.urls import path
from account import views

urlpatterns = [
    # Auth related
    path('login/', views.UserLogin.as_view(), name='login'),
    path('logout/', views.UserLogout.as_view(), name='logout'),
    path('signup/email/', views.UserEmailCheck.as_view(), name='user-email-check'),
    path('signup/password/', views.UserPasswordCheck.as_view(), name='user-password-check'),
    path('signup/username/', views.UserUsernameCheck.as_view(), name='user-username-check'),
    path('signup/birthdate/', views.UserBirthDateCheck.as_view(), name='user-birthdate-check'),
    path('signup/inviter-birthdate/', views.UserInviterBirthDateCheck.as_view(), name='user-inviter-birthdate-check'),
    path('signup/inviter-username/', views.UserInviterUsernameCheck.as_view(), name='user-inviter-username-check'),
    path('signup/', views.UserSignup.as_view(), name='user-signup'),
    path('activate/<uidb64>/<str:token>/', views.UserVerifyEmail.as_view(), name='user-verify-email'),
    path('send-reset-password-email/', views.SendResetPasswordEmail.as_view(), name='user-send-reset-password-email'),
    path('reset-password/<int:pk>/', views.ResetPassword.as_view(), name='user-reset-password'),
    path('reset-password/', views.CurrentUserResetPassword.as_view(), name='current-user-reset-password'),
    path('password-confirm/', views.UserPasswordConfirm.as_view(), name='user-password-confirm'),

    # Current User Related
    path('me/', views.CurrentUserDetail.as_view(), name='current-user-detail'),
    path('me/delete/', views.CurrentUserDelete.as_view(), name='current-user-delete'),
    path('me/profile/', views.CurrentUserProfile.as_view(), name='current-user-profile'),
    path('me/notes/', views.CurrentUserNoteList.as_view(), name='current-user-note-list'),
    path('me/responses/', views.CurrentUserResponseList.as_view(), name='current-user-response-list'),
    path('me/response-requests/', views.ReceivedResponseRequestList.as_view(), name='received-response-request-list'),
    path('me/search/', views.CurrentUserFriendSearch.as_view(), name='current-user-friend-search'),
    path('me/all-posts/', views.CurrentUserAllPostList.as_view(), name='current-user-all-post-list'),
    path('me/latest-visibility/', views.CurrentUserLatestVisibility.as_view(), name='current-user-latest-visibility'),
    path('me/note-status/', views.CurrentUserNoteStatus.as_view(), name='current-user-note-status'),
    path('me/interests/', views.CurrentUserInterestUpdate.as_view(), name='current-user-interest-update'),
    path('me/personas/', views.CurrentUserPersonaUpdate.as_view(), name='current-user-persona-update'),
    path('me/chips/', views.CurrentUserChipsUpdate.as_view(), name='current-user-chips-update'),
    path('me/custom-chips/', views.CustomChipListCreate.as_view(), name='custom-chip-list-create'),
    path('chip-categories/', views.ChipCategoriesView.as_view(), name='chip-categories'),

    # Interest/Persona Search
    path('interests/search/', views.InterestSearch.as_view(), name='interest-search'),
    path('personas/search/', views.PersonaSearch.as_view(), name='persona-search'),

    # Interest/Persona Recommendation
    path('recommendations/interests/', views.InterestRecommendation.as_view(), name='interest-recommendation'),
    path('recommendations/personas/', views.PersonaRecommendation.as_view(), name='persona-recommendation'),

    # User Profile related
    path(r'search/', views.UserSearch.as_view(), name='user-search'),
    path('<str:username>/profile/', views.UserProfile.as_view(), name='user-detail'),
    path('<str:username>/notes/', views.UserNoteList.as_view(), name='user-note-list'),
    path('<str:username>/responses/', views.UserResponseList.as_view(), name='user-response-list'),
    path('<str:username>/friend-list/', views.FriendFriendList.as_view(), name='friend-friend-list'),
    path('<str:username>/all-posts/', views.UserAllPostList.as_view(), name='user-all-post-list'),
    path('<str:username>/unread-posts/', views.UserUnreadPostList.as_view(), name='user-unread-post-list'),
    path('<str:username>/check_in/pinned/', views.UserPinnedCheckInEntries.as_view(), name='user-check-in-pinned'),
    path('mark-all-notes-as-read/', views.UserMarkAllNotesAsRead.as_view(), name='user-mark-all-notes-as-read'),
    path('mark-all-responses-as-read/', views.UserMarkAllResponsesAsRead.as_view(), name='user-mark-all-responses-as-read'),
    path('friends/mark-all-checkins-as-read/', views.FriendsMarkAllCheckInsAsRead.as_view(), name='friends-mark-all-checkins-as-read'),
    path('friends/mark-all-posts-as-read/', views.FriendsMarkAllPostsAsRead.as_view(), name='friends-mark-all-posts-as-read'),

    # Friend List related
    path('friends/', views.FriendList.as_view(), name='friend-list'),
    path('friends/updates/', views.FriendUpdateList.as_view(), name='friend-update-list'),
    path('friends/update/', views.FriendListUpdate.as_view(), name='current-user-friends-update'),

    path('friends/favorites/', views.UserFavoriteAdd.as_view(), name='user-favorite-add'),
    path('friends/<int:pk>/favorites/', views.UserFavoriteDestroy.as_view(), name='user-favorite-destroy'),

    path('friends/hidden/', views.UserHiddenAdd.as_view(), name='user-hidden-add'),
    path('friends/<int:pk>/hidden/', views.UserHiddenDestroy.as_view(), name='user-hidden-destroy'),

    path('connections/<int:pk>/', views.ConnectionChoiceUpdate.as_view(), name='connection-choice-update'),

    # Feed related
    path('feed/', views.FriendFeed.as_view(), name='friend-feed'),
    path('feed/full/', views.FullFriendFeed.as_view(), name='full-friend-feed'),
    path('discover/', views.DiscoverFeedView.as_view(), name='discover-feed'),

    # Friendship related
    path('friends/<int:pk>/', views.UserFriendDestroy.as_view(), name='user-friend-destroy'),

    # FriendRequest related
    path('friend-requests/', views.UserFriendRequest.as_view(),
         name='user-friend-request-list'),
    path('friend-requests/sent/', views.UserSentFriendRequestList.as_view(),
         name='user-sent-friend-request-list'),
    path('friend-requests/<int:pk>/', views.UserFriendRequestDestroy.as_view(),
         name='user-friend-request-destroy'),
    path('friend-requests/<int:pk>/respond/', views.UserFriendRequestUpdate.as_view(),
         name='user-friend-request-update'),

    # Friend Recommend related
    path('recommended-friends/', views.UserRecommendedFriendsList.as_view(), name='user-recommended-friends-list'),
    path('block-recommendation/', views.BlockRecCreate.as_view(), name='block-rec-create'),

     # Subscribe related
    path('friends/subscribe/', views.SubscribeUserContent.as_view(), name='subscribe-user-content'),
    path('friends/<int:pk>/subscribe/', views.UnsubscribeUserContent.as_view(), name='unsubscribe-user-content'),

    # Check-in subscribe (version_w only)
    path('friends/check-in-subscribe/', views.CheckInSubscribeAdd.as_view(), name='check-in-subscribe-add'),
    path('friends/<int:pk>/check-in-subscribe/', views.CheckInSubscribeDestroy.as_view(), name='check-in-subscribe-destroy'),

    # Per-friend multi-type subscriptions (Ver.W 7 types / Ver.Q 2 types)
    path('friends/<int:pk>/subscriptions/', views.FriendSubscriptions.as_view(), name='friend-subscriptions'),

    # TMI Placeholder
    path('tmi-placeholder/', views.TmiPlaceholder.as_view(), name='tmi-placeholder'),

    # User Tracking related
    path("app-sessions/start/", views.StartSession.as_view(), name="start_session"),
    path("app-sessions/end/", views.EndSession.as_view(), name="end_session"),
    path("app-sessions/touch/", views.TouchSession.as_view(), name="touch_session"),

    # Version Swap Request
    path('version-swap-request/', views.VersionSwapRequestCreate.as_view(), name='version-swap-request-create'),
    path('version-swap-request/me/', views.CurrentUserVersionSwapRequest.as_view(), name='current-user-version-swap-request'),
]
