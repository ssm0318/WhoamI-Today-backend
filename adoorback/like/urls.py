from django.urls import path

from like import views

urlpatterns = [
    path('', views.LikeCreate.as_view(), name='like-list'),
    path('<int:pk>/', views.LikeDestroy.as_view(), name='like-destroy'),
]
