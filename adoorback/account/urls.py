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
    path('select-questions/', views.SignupQuestions.as_view(),
         name='signup-questions'),
    path('send-reset-password-email/', views.SendResetPasswordEmail.as_view(), name='user-send-reset-password-email'),
    path('reset-password/<int:pk>/<str:token>/', views.ResetPasswordWithToken.as_view(), name='user-reset-password-with-token'),
    path('reset-password/<int:pk>/', views.ResetPassword.as_view(), name='user-reset-password'),
    path('password-confirm/', views.UserPasswordConfirm.as_view(), name='user-password-confirm'),

    # User Profile related
    path('', views.UserList.as_view(), name='user-list'),
    path(r'search/', views.UserSearch.as_view(), name='user-search'),
    path('profile/<str:username>/', views.UserDetail.as_view(), name='user-detail'),

    # Current User Related
    path('me/', views.CurrentUserProfile.as_view(), name='current-user'),
    path('me/friends/', views.CurrentUserFriendList.as_view(), name='current-user-friends'),
    path('me/friends/all/', views.CurrentUserFriendDetailList.as_view(), name='current-user-friends-detail'),
    path('me/friends/edit/', views.CurrentUserFriendEditList.as_view(), name='current-user-friends-edit'),
    path('me/friends/updated/', views.CurrentUserFriendUpdatedList.as_view(), name='current-user-friends-updated'),
    path('me/favorites/', views.CurrentUserFavoritesList.as_view(), name='current-user-favorites'),
    path('me/friends/update/', views.CurrentUserFriendsUpdate.as_view(), name='current-user-friends-update'),
    path('me/delete/', views.CurrentUserDelete.as_view() , name='current-user-delete'),

    # Friendship related
    path('friend/<int:pk>/', views.UserFriendDestroy.as_view(), name='user-friend-destroy'),

    # Favorites related
    path('favorite/add/', views.UserFavoriteAdd.as_view(), name='user-favorite-add'),
    path('favorite/<int:pk>/', views.UserFavoriteDestroy.as_view(), name='user-favorite-destroy'),

    # Hidden related
    path('hidden/add/', views.UserHiddenAdd.as_view(), name='user-hidden-add'),

    # FriendRequest related
    path('friend-requests/', views.UserFriendRequestList.as_view(),
         name='user-friend-request-list'),
    path('sent-friend-requests/', views.UserSentFriendRequestList.as_view(),
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

    path('friends/today/', views.TodayFriends.as_view(), name='today-friends'),
    path('friend/<int:pk>/today/', views.TodayFriend.as_view(), name='today-friend')
]
