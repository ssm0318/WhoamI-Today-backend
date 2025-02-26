from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.static import serve
from django.conf.urls.i18n import i18n_patterns
from django.http import JsonResponse

def health_check(request):
    return JsonResponse({"status": "ok"}, status=200)

urlpatterns = [
    path("api/health/", health_check),
]

urlpatterns += i18n_patterns(
    path('api/content_reports/', include('content_report.urls')),
    path('api/user_reports/', include('user_report.urls')),
    path('api/user_tags/', include('user_tag.urls')),
    path('api/likes/', include('like.urls')),
    path('api/comments/', include('comment.urls')),
    path('api/notifications/', include('notification.urls')),
    path('api/qna/', include('qna.urls')),
    path('api/user/', include('account.urls')),
    path('api/reactions/', include('reaction.urls')),
    path('api/check_in/', include('check_in.urls')),
    path('api/notes/', include('note.urls')),
    
    path('api/secret/', admin.site.urls),
    path('api/user/', include('rest_framework.urls', namespace='rest_framework')),
    path('api/', include('custom_fcm.urls')), 
    path('api/tracking/', include('tracking.urls')),
    path('api/chat/', include('chat.urls')),
    path('api/ping/', include('ping.urls')),

    path('api/translate/', include('translate.urls')),
    prefix_default_language=False
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
        re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
    ]