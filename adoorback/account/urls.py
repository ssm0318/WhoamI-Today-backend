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
    path('me/delete/', views.CurrentUserDelete.as_view() , name='current-user-delete'),
 
    # Friendship related
    path('friend/<int:pk>/', views.UserFriendDestroy.as_view(), name='user-friend-destroy'),

    # FriendRequest related
    path('friend-requests/', views.UserFriendRequestList.as_view(),
         name='user-friend-request-list'),
    path('friend-requests/<int:pk>/', views.UserFriendRequestDestroy.as_view(),
         name='user-friend-request-destroy'),
    path('friend-requests/<int:pk>/respond/', views.UserFriendRequestUpdate.as_view(),
         name='user-friend-request-update'),
]
