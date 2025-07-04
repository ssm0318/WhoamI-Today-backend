from django.urls import path

from note import views

urlpatterns = [
    path('', views.NoteCreate.as_view(), name='note-list'),
    path('<int:pk>/', views.NoteDetail.as_view(), name='note-detail'),
    path('<int:pk>/default/', views.DefaultFriendNoteDetail.as_view(), name='default-friend-note-detail'),
    path('<int:pk>/comments/', views.NoteComments.as_view(), name='note-comments'),
    path('<int:pk>/likes/', views.NoteLikes.as_view(), name='note-likes'),  # for default ver.
    path('<int:pk>/interactions/', views.NoteInteractions.as_view(), name='note-interaction-user-list'),
    path('read/', views.NoteRead.as_view(), name='note-read'),

    path('notice/', views.NoticeList.as_view(), name='notice-list'),
    path('notice/<int:pk>/', views.NoticeDetail.as_view(), name='notice-detail'),
    path('notice/<int:pk>/comments/', views.NoticeComments.as_view(), name='notice-comments'),
    path('notice/<int:pk>/interactions/', views.NoticeInteractions.as_view(), name='notice-interaction-user-list'),
    path('notice/mark-all-notices-as-read/', views.UserMarkAllNoticesAsRead.as_view(), name='user-mark-all-notices-as-read'),
]
