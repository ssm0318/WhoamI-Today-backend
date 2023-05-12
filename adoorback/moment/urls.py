from django.urls import path
from moment import views

urlpatterns = [
    path('moments/', views.MomentList.as_view(), name='moment-list'),
]
