from django.urls import path

from note import views

urlpatterns = [
    path('', views.NoteList.as_view(), name='note-list'),
]
