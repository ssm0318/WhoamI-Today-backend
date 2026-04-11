from django.urls import path
from note import views_q

urlpatterns = [
    path('', views_q.QNoteCreate.as_view(), name='q-note-create'),
    path('<int:pk>/', views_q.QNoteDetail.as_view(), name='q-note-detail'),
]
