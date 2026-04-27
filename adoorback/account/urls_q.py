from django.urls import path
from account import views_q

urlpatterns = [
    # Current User (Q: no chips_by_category, no custom_chips)
    path('me/', views_q.QCurrentUserDetail.as_view(), name='q-current-user-detail'),
    path('me/notes/', views_q.QCurrentUserNoteList.as_view(), name='q-current-user-note-list'),
    path('me/all-posts/', views_q.QCurrentUserAllPostList.as_view(), name='q-current-user-all-post-list'),

    # User Profile (Q: no chip fields)
    path('<str:username>/profile/', views_q.QUserProfile.as_view(), name='q-user-detail'),
    path('<str:username>/notes/', views_q.QUserNoteList.as_view(), name='q-user-note-list'),
    path('<str:username>/all-posts/', views_q.QUserAllPostList.as_view(), name='q-user-all-post-list'),

    # Feed (Q: notes only with Q serializer)
    path('feed/', views_q.QFriendFeed.as_view(), name='q-friend-feed'),

    # Discover (Q: public posts from non-friends, reverse chronological)
    path('discover/', views_q.QDiscoverFeed.as_view(), name='q-discover-feed'),
]
