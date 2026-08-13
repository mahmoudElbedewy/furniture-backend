from django.urls import path
from . import views

urlpatterns = [
    path('start/', views.ChatStartView.as_view(), name='chat-start'),
    path('unread/', views.CustomerUnreadView.as_view(), name='chat-unread'),
    path('push-config/', views.WebPushConfigView.as_view(), name='chat-push-config'),
    path('push-subscriptions/', views.CustomerPushSubscriptionView.as_view(), name='chat-push-subscriptions'),
    path('<uuid:conversation_id>/history/', views.ChatHistoryView.as_view(), name='chat-history'),
    path('<uuid:conversation_id>/context/', views.ChatBrowsingContextView.as_view(), name='chat-context'),
    path('<uuid:conversation_id>/send/', views.ChatSendMessageView.as_view(), name='chat-send'),
    path('ntfy-test/', views.ntfy_test_view, name='ntfy_test_view'),
]
