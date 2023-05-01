from django.urls import path

from content_report import views

urlpatterns = [
    path('', views.ContentReportList.as_view(), name='content-report-list'),
]
