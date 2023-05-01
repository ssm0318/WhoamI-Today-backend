from django.urls import path
from feed import views

urlpatterns = [
    # Feed related
    path('friend/', views.FriendFeedPostList.as_view(), name='friend-feed-post-list'),
    path('anonymous/', views.AnonymousFeedPostList.as_view(), name='anonymous-feed-post-list'),
    path('user/<int:pk>/', views.UserFeedPostList.as_view(), name='user-feed-post-list'),

    # Article related
    path('articles/', views.ArticleList.as_view(), name='article-list'),
    path('articles/<int:pk>/', views.ArticleDetail.as_view(), name='article-detail'),

    # Response related
    path('responses/', views.ResponseList.as_view(), name='response-list'),
    path('responses/<int:pk>/', views.ResponseDetail.as_view(), name='response-detail'),

    # Question related
    path('questions/daily/', views.DailyQuestionList.as_view(), name='daily-question-list'),
    path('questions/daily/recommended/',
         views.RecommendedQuestionList.as_view(), name='recommended-question-list'),
    path('questions/', views.QuestionList.as_view(), name='question-list'),

    # Question Detail Page related
    path('questions/<int:pk>/', views.QuestionAllResponsesDetail.as_view(), name='question-detail'),
    path('questions/<int:pk>/friend/',
         views.QuestionFriendResponsesDetail.as_view(), name='question-detail-friend'),
    path('questions/<int:pk>/anonymous/',
         views.QuestionAnonymousResponsesDetail.as_view(), name='question-detail-anonymous'),

    # Response Request related
    path('questions/response-request/', views.ResponseRequestCreate.as_view(),
         name='response-request-create'),
    path('questions/<int:qid>/response-request/', views.ResponseRequestList.as_view(),
         name='response-request-list'),
    path('questions/<int:qid>/response-request/<int:rid>/', views.ResponseRequestDestroy.as_view(),
         name='response-request-destroy'),
]
