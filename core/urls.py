from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from core.track_views import TrackVisitView, TrackFunnelEventView
from core import analytics_bridge_views
from core import meta_oauth_views


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    
    path('api/auth/', include('accounts.urls')),
    path('api/catalog/', include('catalog.urls')),
    path('api/orders/', include('orders.urls')),
    path('api/chat/', include('chat.urls')),
    path('api/admin/', include('core.admin_urls')),
    path('api/telegram/', include('telegram_bot.urls')),
    path('api/track-visit/', TrackVisitView.as_view(), name='track-visit'),
    path('api/analytics/bridge/sync/', analytics_bridge_views.trigger_sync),
    path('api/track-funnel-event/', TrackFunnelEventView.as_view(), name='track-funnel-event'),
    path('api/meta/oauth/callback/', meta_oauth_views.MetaOAuthCallbackView.as_view(), name='meta-oauth-callback'),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
