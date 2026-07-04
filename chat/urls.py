from django.urls import path
from . import views

urlpatterns = [
    path('start/', views.ChatStartView.as_view(), name='chat-start'),
    path('<uuid:conversation_id>/history/', views.ChatHistoryView.as_view(), name='chat-history'),
    path('<uuid:conversation_id>/send/', views.ChatSendMessageView.as_view(), name='chat-send'),
]
