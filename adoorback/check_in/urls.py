from django.urls import path
from check_in import views

urlpatterns = [
    path('', views.CurrentCheckIn.as_view(), name='current-check-in'),
    path('<int:pk>/', views.CheckInDetail.as_view(), name='check-in-detail'),
    path('read/<int:pk>/', views.CheckInRead.as_view(), name='check-in-read'),
    path('latest-visibility/', views.CurrentUserLatestCheckInVisibility.as_view(), name='current-user-latest-check-in-visibility'),
    path('latest/', views.LatestCheckIn.as_view(), name='latest-check-in'),

    path('components/<str:component>/archive/', views.ArchiveLiveComponent.as_view(), name='archive-live-component'),

    path('entries/', views.OwnArchiveEntries.as_view(), name='own-archive-entries'),
    path('entries/<int:pk>/', views.ArchiveEntryDelete.as_view(), name='archive-entry-delete'),
    path('entries/<int:pk>/pin/', views.ArchiveEntryPinToggle.as_view(), name='archive-entry-pin'),
    path('entries/<int:pk>/pin_visibility/', views.ArchiveEntryPinVisibility.as_view(), name='archive-entry-pin-visibility'),

    path('song/', views.CurrentSong.as_view(), name='current-song'),
    path('song/<int:pk>/', views.SongDetail.as_view(), name='my-song-detail'),

    path('<int:pk>/react/', views.CheckInReact.as_view(), name='check-in-react'),
    path('<int:pk>/reactions/', views.CheckInReactions.as_view(), name='check-in-reactions'),

    path('poke/', views.PokeCreate.as_view(), name='poke-create'),
    path('poke/sent/', views.PokeSent.as_view(), name='poke-sent'),
    path('poke/<int:pk>/', views.PokeDelete.as_view(), name='poke-delete'),

    # Ver.Q image+text "check-in" posts
    path('posts/', views.CheckInPostFeed.as_view(), name='check-in-post-feed'),
    path('posts/stories/', views.CheckInPostStories.as_view(), name='check-in-post-stories'),
    path('posts/<int:pk>/', views.CheckInPostDetail.as_view(), name='check-in-post-detail'),
    path('posts/<int:pk>/comments/', views.CheckInPostComments.as_view(), name='check-in-post-comments'),
    path('posts/<int:pk>/pin/', views.CheckInPostPinToggle.as_view(), name='check-in-post-pin'),
    path('posts/<int:pk>/visibility/', views.CheckInPostVisibility.as_view(), name='check-in-post-visibility'),
    path('posts/<int:pk>/pin_visibility/', views.CheckInPostPinVisibility.as_view(), name='check-in-post-pin-visibility'),
    path('posts/read/', views.CheckInPostRead.as_view(), name='check-in-post-read'),
    path('posts/by-user/<int:pk>/', views.UserCheckInPosts.as_view(), name='check-in-posts-by-user'),
]
