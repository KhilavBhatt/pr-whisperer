from django.contrib import admin
from django.urls import path, include
from integrations.urls import webhook_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('integrations.urls')),
    path('api/webhooks/', include(webhook_urlpatterns)),
]
