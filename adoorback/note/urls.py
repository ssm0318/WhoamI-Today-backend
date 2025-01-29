from django.urls import path

from note import views

urlpatterns = [
    path('', views.NoteCreate.as_view(), name='note-list'),
    path('default/', views.DefaultFriendNoteCreate.as_view(), name='default-friend-note-list'),
    path('<int:pk>/', views.NoteDetail.as_view(), name='note-detail'),
    path('<int:pk>/default/', views.DefaultFriendNoteDetail.as_view(), name='default-friend-note-detail'),
    path('<int:pk>/comments/', views.NoteComments.as_view(), name='note-comments'),
    path('<int:pk>/likes/', views.NoteLikes.as_view(), name='note-likes'),  # for default ver.
    path('<int:pk>/interactions/', views.NoteInteractions.as_view(), name='note-interaction-user-list'),
    path('read/', views.NoteRead.as_view(), name='note-read'),
]
