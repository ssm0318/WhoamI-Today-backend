from django.urls import path
from playlist import views

urlpatterns = [
    path('feed/', views.SongList.as_view(), name='playlist-feed'),
    path('<int:pk>/', views.SongDetail.as_view(), name='song-detail'),
]
