from django.urls import path
from . import views

urlpatterns = [
    path('', views.OrderCreateView.as_view(), name='order-create'),
    path('mine/', views.MyOrdersView.as_view(), name='my-orders'),
    path('track/<str:order_number>/', views.OrderTrackView.as_view(), name='order-track'),
    path('abandoned/', views.AbandonedCartCreateView.as_view(), name='abandoned-cart'),
]
