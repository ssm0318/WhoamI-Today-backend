from django.urls import path
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from account import views

urlpatterns = [
    # Token related
    path('token/', ensure_csrf_cookie(views.CustomTokenObtainPairView.as_view()), name='token-obtain-pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token-verify'),

    # Auth related
    path('signup/', views.UserSignup.as_view(), name='user-signup'),
    path('activate/<int:pk>/<str:token>/', views.UserActivate.as_view(), name='user-activate'),
    path('select-questions/', views.SignupQuestions.as_view(),
         name='signup-questions'),
    path('send-reset-password-email/', views.SendResetPasswordEmail.as_view(), name='user-send-reset-password-email'),
    path('reset-password/<int:pk>/<str:token>/', views.ResetPassword.as_view(), name='user-reset-password'),

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
