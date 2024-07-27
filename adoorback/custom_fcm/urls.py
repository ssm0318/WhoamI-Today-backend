from django.urls import path
from .views import FCMRegisterView

urlpatterns = [
    path('register/', FCMRegisterView.as_view(), name='fcm_register'),
]