from django.urls import path

from surveys.views import (
    PastSurveysView, SurveyDetailView, SurveyOfTheDayView,
    SurveyResponseSubmitView, SurveyResultsView,
)

urlpatterns = [
    path('today/', SurveyOfTheDayView.as_view(), name='survey-today'),
    path('past/', PastSurveysView.as_view(), name='survey-past'),
    path('<slug:slug>/', SurveyDetailView.as_view(), name='survey-detail'),
    path('<slug:slug>/responses/', SurveyResponseSubmitView.as_view(), name='survey-submit'),
    path('<slug:slug>/results/', SurveyResultsView.as_view(), name='survey-results'),
]
