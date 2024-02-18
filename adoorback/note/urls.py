from django.urls import path

from note import views

urlpatterns = [
    path('', views.NoteList.as_view(), name='note-list'),
    path('<int:pk>/', views.NoteDetail.as_view(), name='note-detail'),
    path('comments/<int:pk>/', views.NoteComments.as_view(), name='note-comments'),
]
