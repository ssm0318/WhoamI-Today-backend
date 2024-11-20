from django.urls import path
from category import views

app_name = 'category'

urlpatterns = [
    path('', views.CategoryListCreateView.as_view(), name='category-list'),
    path('<int:pk>/', views.CategoryDetailView.as_view(), name='category-detail'),
    path('<int:pk>/subscribe/', views.SubscriptionListCreateView.as_view(), name='subscription-create'),
    path('<int:pk>/unsubscribe/', views.SubscriptionDestroyView.as_view(), name='subscription-destroy'),
]