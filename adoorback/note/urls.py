from django.urls import path

from note import views

urlpatterns = [
    path('', views.NoteCreate.as_view(), name='note-list'),
    path('<int:pk>/', views.NoteDetail.as_view(), name='note-detail'),
    path('<int:pk>/comments/', views.NoteComments.as_view(), name='note-comments'),
    path('<int:pk>/likes/', views.NoteLikes.as_view(), name='note-like-user-list'),
    path('read/', views.NoteRead.as_view(), name='note-read'),
]
