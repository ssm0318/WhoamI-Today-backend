from django.urls import path

from user_report import views

urlpatterns = [
    path('', views.UserReportList.as_view(), name='user-report-list'),
]