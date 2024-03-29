from django.urls import path
from account import views

urlpatterns = [
    # Auth related
    path('login/', views.UserLogin.as_view(), name='login'),
    path('logout/', views.UserLogout.as_view(), name='logout'),
    path('signup/email/', views.UserEmailCheck.as_view(), name='user-email-check'),
    path('signup/password/', views.UserPasswordCheck.as_view(), name='user-password-check'),
    path('signup/username/', views.UserUsernameCheck.as_view(), name='user-username-check'),
    path('signup/', views.UserSignup.as_view(), name='user-signup'),
    path('signup/questions/', views.SignupQuestions.as_view(),
         name='signup-questions'),
    path('send-reset-password-email/', views.SendResetPasswordEmail.as_view(), name='user-send-reset-password-email'),
    path('reset-password/<int:pk>/<str:token>/', views.ResetPasswordWithToken.as_view(), name='user-reset-password-with-token'),
    path('reset-password/<int:pk>/', views.ResetPassword.as_view(), name='user-reset-password'),
    path('password-confirm/', views.UserPasswordConfirm.as_view(), name='user-password-confirm'),

    # Current User Related
    path('me/', views.CurrentUserDetail.as_view(), name='current-user-detail'),
    path('me/delete/', views.CurrentUserDelete.as_view(), name='current-user-delete'),
    path('me/profile/', views.CurrentUserProfile.as_view(), name='current-user-profile'),
    path('me/notes/', views.CurrentUserNoteList.as_view(), name='current-user-note-list'),
    path('me/responses/', views.CurrentUserResponseList.as_view(), name='current-user-response-list'),

    # User Profile related
    path(r'search/', views.UserSearch.as_view(), name='user-search'),
    path('<str:username>/profile/', views.UserProfile.as_view(), name='user-detail'),
    path('<str:username>/notes/', views.UserNoteList.as_view(), name='user-note-list'),
    path('<str:username>/responses/', views.UserResponseList.as_view(), name='user-response-list'),

    # Friend List related
    path('friends/', views.FriendList.as_view(), name='friend-list'),
    path('friends/update/', views.FriendListUpdate.as_view(), name='current-user-friends-update'),

    path('friends/favorites/', views.UserFavoriteAdd.as_view(), name='user-favorite-add'),
    path('friends/<int:pk>/favorites/', views.UserFavoriteDestroy.as_view(), name='user-favorite-destroy'),

    path('friends/hidden/', views.UserHiddenAdd.as_view(), name='user-hidden-add'),
    path('friends/<int:pk>/hidden/', views.UserHiddenDestroy.as_view(), name='user-hidden-destroy'),

    # Friendship related
    path('friends/<int:pk>/', views.UserFriendDestroy.as_view(), name='user-friend-destroy'),

    # FriendRequest related
    path('friend-requests/', views.UserFriendRequestListCreate.as_view(),
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

    # FriendGroup related
    path('friend-groups/', views.UserFriendGroupList.as_view(),
         name='user-friend-group-list'),
    path('friend-groups/create/', views.UserFriendGroupCreate.as_view(),
         name='user-friend-group-create'),
    path('friend-groups/order/', views.UserFriendGroupOrderUpdate.as_view(),
         name='user-friend-group-order-update'),
    path('friend-groups/<int:pk>/', views.UserFriendGroupDetail.as_view(),
         name='user-friend-request-detail'),
]
