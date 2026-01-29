from django.urls import path
from check_in import views

urlpatterns = [
    path('', views.CurrentCheckIn.as_view(), name='current-check-in'),
    path('<int:pk>/', views.CheckInDetail.as_view(), name='check-in-detail'),
    path('read/<int:pk>/', views.CheckInRead.as_view(), name='check-in-read'),
    path('latest-visibility/', views.CurrentUserLatestCheckInVisibility.as_view(), name='current-user-latest-check-in-visibility'),
]
