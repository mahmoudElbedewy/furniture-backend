from django.urls import path, include
from rest_framework.routers import DefaultRouter
from catalog.admin_views import AdminProductViewSet, AdminCategoryViewSet
from orders.admin_views import AdminOrderViewSet
from . import admin_views
from . import analytics_views
from . import meta_oauth_views
from core import meta_oauth_views

router = DefaultRouter()
router.register(r'products', AdminProductViewSet, basename='admin-product')
router.register(r'categories', AdminCategoryViewSet, basename='admin-category')
router.register(r'orders', AdminOrderViewSet, basename='admin-order')
router.register(r'chats', admin_views.ChatAdminViewSet, basename='admin-chat')
router.register(r'agent-actions', admin_views.AgentActionRequestViewSet, basename='admin-agent-action')
router.register(r'commissions', admin_views.CommissionViewSet, basename='admin-commission')
router.register(r'suppliers', admin_views.AdminSupplierViewSet, basename='admin-supplier')
router.register(r'notifications', admin_views.AdminNotificationViewSet, basename='admin-notification')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/stats/', admin_views.DashboardStatsView.as_view(), name='admin-dashboard-stats'),
    path('chats/<uuid:pk>/reply/', admin_views.ChatAdminReplyView.as_view(), name='admin-chat-reply'),
    path('agent-settings/', admin_views.AgentSettingsView.as_view(), name='admin-agent-settings'),
    path('agent/product-images/', admin_views.AgentProductImageView.as_view(), name='admin-agent-product-images'),
    path('agent/product-draft/', admin_views.AgentProductDraftView.as_view(), name='admin-agent-product-draft'),
    
    # Analytics Dashboard Endpoints
    path('analytics/overview/', analytics_views.AnalyticsOverviewView.as_view(), name='admin-analytics-overview'),
    path('analytics/sales/', analytics_views.AnalyticsSalesView.as_view(), name='admin-analytics-sales'),
    path('analytics/audience/', analytics_views.AnalyticsAudienceView.as_view(), name='admin-analytics-audience'),
    path('analytics/content/', analytics_views.AnalyticsContentView.as_view(), name='admin-analytics-content'),
    path('analytics/web/', analytics_views.AnalyticsWebView.as_view(), name='admin-analytics-web'),
    path('analytics/meta/', analytics_views.AnalyticsMetaView.as_view(), name='admin-analytics-meta'),
    path('analytics/posts/<str:post_id>/drilldown/', analytics_views.AnalyticsPostDrilldownView.as_view(), name='admin-analytics-drilldown'),
    path('analytics/settings/', analytics_views.AnalyticsSettingsView.as_view(), name='admin-analytics-settings'),
    path('analytics/sync-now/', analytics_views.AnalyticsSyncNowView.as_view(), name='admin-analytics-sync-now'),
    path('analytics/meta/oauth/start/', meta_oauth_views.MetaOAuthStartView.as_view(), name='admin-analytics-meta-oauth-start'),
    path('analytics/sales/funnel/', analytics_views.AnalyticsSalesFunnelView.as_view(), name='admin-analytics-sales-funnel'),
    path('analytics/products/top/', analytics_views.AnalyticsProductsTopView.as_view(), name='admin-analytics-products-top'),
    path('analytics/products/categories/', analytics_views.AnalyticsProductsCategoriesView.as_view(), name='admin-analytics-products-categories'),
    path('analytics/products/underperforming/', analytics_views.AnalyticsProductsUnderperformingView.as_view(), name='admin-analytics-products-underperforming'),
    path('analytics/favorites/', analytics_views.AnalyticsFavoritesView.as_view(), name='admin-analytics-favorites'),
    path('analytics/realtime/', analytics_views.AnalyticsRealtimeView.as_view(), name='admin-analytics-realtime'),
    path('analytics/customers/ltv/', analytics_views.AnalyticsCustomersLTVView.as_view(), name='admin-analytics-customers-ltv'),
    path('analytics/search/', analytics_views.AnalyticsSearchView.as_view(), name='admin-analytics-search'),
    # Alerts
    path('analytics/alerts/', analytics_views.AnalyticsAlertsView.as_view(), name='admin-analytics-alerts'),
    path('analytics/alerts/read-all/', analytics_views.AnalyticsAlertReadAllView.as_view(), name='admin-analytics-alerts-read-all'),
    path('analytics/alerts/trigger/', analytics_views.AnalyticsTriggerAlertsView.as_view(), name='admin-analytics-alerts-trigger'),
    path('analytics/alerts/<int:pk>/read/', analytics_views.AnalyticsAlertReadView.as_view(), name='admin-analytics-alert-read'),
]
