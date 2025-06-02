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
    path('me/notes/default/', views.DefaultCurrentUserNoteList.as_view(), name='default-current-user-note-list'),
    path('me/responses/', views.CurrentUserResponseList.as_view(), name='current-user-response-list'),
    path('me/response-requests/', views.ReceivedResponseRequestList.as_view(), name='received-response-request-list'),
    path('me/search/', views.CurrentUserFriendSearch.as_view(), name='current-user-friend-search'),

    # User Profile related
    path(r'search/', views.UserSearch.as_view(), name='user-search'),
    path('<str:username>/profile/', views.UserProfile.as_view(), name='user-detail'),
    path('<str:username>/notes/', views.UserNoteList.as_view(), name='user-note-list'),
    path('<str:username>/notes/default/', views.DefaultUserNoteList.as_view(), name='default-user-note-list'),
    path('<str:username>/responses/', views.UserResponseList.as_view(), name='user-response-list'),
    path('<str:username>/friend-list/', views.FriendFriendList.as_view(), name='friend-friend-list'),
    path('mark-all-notes-as-read/', views.UserMarkAllNotesAsRead.as_view(), name='user-mark-all-as-read'),
    path('mark-all-responses-as-read/', views.UserMarkAllResponsesAsRead.as_view(), name='user-mark-all-as-read'),

    # Friend List related
    path('friends/', views.FriendList.as_view(), name='friend-list'),
    path('friends/update/', views.FriendListUpdate.as_view(), name='current-user-friends-update'),

    path('friends/favorites/', views.UserFavoriteAdd.as_view(), name='user-favorite-add'),
    path('friends/<int:pk>/favorites/', views.UserFavoriteDestroy.as_view(), name='user-favorite-destroy'),

    path('friends/hidden/', views.UserHiddenAdd.as_view(), name='user-hidden-add'),
    path('friends/<int:pk>/hidden/', views.UserHiddenDestroy.as_view(), name='user-hidden-destroy'),

    path('connections/<int:pk>/', views.ConnectionChoiceUpdate.as_view(), name='connection-choice-update'),

    # Feed related
    path('feed/', views.FriendFeed.as_view(), name='friend-feed'),
    path('feed/full/', views.FullFriendFeed.as_view(), name='full-friend-feed'),

    # Friendship related
    path('friends/<int:pk>/', views.UserFriendDestroy.as_view(), name='user-friend-destroy'),

    # FriendRequest related
    path('friend-requests/', views.UserFriendRequest.as_view(),
         name='user-friend-request-list'),
    path('friend-requests/default/', views.UserFriendRequestDefault.as_view(), 
         name='user-friend-request-default'),
    path('friend-requests/sent/', views.UserSentFriendRequestList.as_view(),
         name='user-sent-friend-request-list'),
    path('friend-requests/<int:pk>/', views.UserFriendRequestDestroy.as_view(),
         name='user-friend-request-destroy'),
    path('friend-requests/<int:pk>/respond/', views.UserFriendRequestUpdate.as_view(),
         name='user-friend-request-update'),
    path('friend-requests/<int:pk>/respond/default/', views.UserFriendRequestUpdateDefault.as_view(), 
         name='user-friend-request-update-default'),

    # Friend Recommend related
    path('recommended-friends/', views.UserRecommendedFriendsList.as_view(), name='user-recommended-friends-list'),
    path('block-recommendation/', views.BlockRecCreate.as_view(), name='block-rec-create'),

     # Subscribe related
    path('friends/subscribe/', views.SubscribeUserContent.as_view(), name='subscribe-user-content'),
    path('friends/<int:pk>/subscribe/', views.UnsubscribeUserContent.as_view(), name='unsubscribe-user-content'),

    # User Tracking related
    path("app-sessions/start/", views.StartSession.as_view(), name="start_session"),
    path("app-sessions/end/", views.EndSession.as_view(), name="end_session"),
    path("app-sessions/touch/", views.TouchSession.as_view(), name="touch_session"),
]
