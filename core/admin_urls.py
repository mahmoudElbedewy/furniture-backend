from django.urls import path, include
from rest_framework.routers import DefaultRouter
from catalog.admin_views import AdminProductViewSet, AdminCategoryViewSet
from orders.admin_views import AdminOrderViewSet
from . import admin_views

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
]
