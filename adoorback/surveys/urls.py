from django.urls import path

from surveys.views import (
    DropoutSurveyContextView, DropoutSurveyDraftLoadView, DropoutSurveyDraftView,
    DropoutSurveyResponseSubmitView, MyResponseView, PastSurveysView, ReimbursementView,
    SurveyDetailView, SurveyDraftView, SurveyIndexView, SurveyOfTheDayView,
    SurveyResponseSubmitView, SurveyResultsView,
)

urlpatterns = [
    path('dropout/context/', DropoutSurveyContextView.as_view(), name='dropout-survey-context'),
    path('dropout/responses/', DropoutSurveyResponseSubmitView.as_view(), name='dropout-survey-submit'),
    path('dropout/draft/', DropoutSurveyDraftView.as_view(), name='dropout-survey-draft'),
    path('dropout/draft/load/', DropoutSurveyDraftLoadView.as_view(), name='dropout-survey-draft-load'),
    path('today/', SurveyOfTheDayView.as_view(), name='survey-today'),
    path('index/', SurveyIndexView.as_view(), name='survey-index'),
    path('past/', PastSurveysView.as_view(), name='survey-past'),
    path('reimbursement/', ReimbursementView.as_view(), name='survey-reimbursement'),
    path('<slug:slug>/', SurveyDetailView.as_view(), name='survey-detail'),
    path('<slug:slug>/draft/', SurveyDraftView.as_view(), name='survey-draft'),
    path('<slug:slug>/responses/', SurveyResponseSubmitView.as_view(), name='survey-submit'),
    path('<slug:slug>/my_response/', MyResponseView.as_view(), name='survey-my-response'),
    path('<slug:slug>/results/', SurveyResultsView.as_view(), name='survey-results'),
]
