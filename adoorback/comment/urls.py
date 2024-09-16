from django.urls import path

from comment import views

urlpatterns = [
    path('', views.CommentCreate.as_view(), name='comment-create'),
    path('<int:pk>/', views.CommentDetail.as_view(), name='comment-detail'),
    path('<int:pk>/likes/', views.CommentLikes.as_view(), name='comment-like-user-list'),
]
