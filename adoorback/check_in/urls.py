from django.urls import path
from check_in import views

urlpatterns = [
    path('', views.CurrentCheckIn.as_view(), name='current-check-in'),
    path('<int:pk>/', views.CheckInDetail.as_view(), name='check-in-detail'),
    path('read/<int:pk>/', views.CheckInRead.as_view(), name='check-in-read'),
    path('latest-visibility/', views.CurrentUserLatestCheckInVisibility.as_view(), name='current-user-latest-check-in-visibility'),
    path('latest/', views.LatestCheckIn.as_view(), name='latest-check-in'),

    path('song/', views.CurrentSong.as_view(), name='current-song'),
    path('song/<int:pk>/', views.SongDetail.as_view(), name='my-song-detail'),

    path('<int:pk>/react/', views.CheckInReact.as_view(), name='check-in-react'),
    path('<int:pk>/reactions/', views.CheckInReactions.as_view(), name='check-in-reactions'),

    path('poke/', views.PokeCreate.as_view(), name='poke-create'),
    path('poke/sent/', views.PokeSent.as_view(), name='poke-sent'),
    path('poke/<int:pk>/', views.PokeDelete.as_view(), name='poke-delete'),
]
