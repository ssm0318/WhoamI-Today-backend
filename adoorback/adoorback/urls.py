"""adoorback URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.static import serve
from django.conf.urls.i18n import i18n_patterns


urlpatterns = i18n_patterns(
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

    path('api/translate/', include('translate.urls')),
    prefix_default_language=False
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += [
        path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
        path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
    ]
