from django.urls import path
from pin import views

urlpatterns = [
    path('', views.PinCreate.as_view(), name='pin-create'),
    path('<int:pk>/', views.PinDestroy.as_view(), name='pin-destroy'),
    path('me/', views.MyPinList.as_view(), name='my-pin-list'),
    path('users/<str:username>/', views.UserPinList.as_view(), name='user-pin-list'),
]
