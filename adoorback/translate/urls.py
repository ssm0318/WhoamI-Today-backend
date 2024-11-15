from django.urls import path

from translate import views

urlpatterns = [
    path('', views.TranslateV2.as_view()),
]
