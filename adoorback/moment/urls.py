from django.urls import path
from moment import views

urlpatterns = [
    path('today/', views.MomentToday.as_view(), name='moment-today'),
]
