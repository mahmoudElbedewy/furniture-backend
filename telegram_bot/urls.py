from django.urls import path
from . import views
from . import bridge_views

urlpatterns = [
    path('webhook/', views.TelegramWebhookView.as_view(), name='telegram-webhook'),
    path("bridge/pending/", bridge_views.pending_notifications),
    path("bridge/mark-sent/<int:notification_id>/", bridge_views.mark_sent),
    path("bridge/offset/", bridge_views.offset_view),
    path("bridge/approve/<str:order_number>/", bridge_views.approve_order),
    path("bridge/reject/<str:order_number>/", bridge_views.reject_order),
    path("bridge/agent-approve/<str:req_id>/", bridge_views.approve_agent_action),
    path("bridge/agent-reject/<str:req_id>/", bridge_views.reject_agent_action),
]