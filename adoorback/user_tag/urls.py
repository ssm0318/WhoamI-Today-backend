from django.urls import path

from user_tag import views

urlpatterns = [
    path('search/', views.UserTagSearch.as_view(), name='user_tag-search')
]
