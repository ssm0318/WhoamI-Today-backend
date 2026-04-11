from django.urls import path
from qna import views_q

urlpatterns = [
    path('responses/', views_q.QResponseCreate.as_view(), name='q-response-create'),
    path('responses/<int:pk>/', views_q.QResponseDetail.as_view(), name='q-response-detail'),
]
