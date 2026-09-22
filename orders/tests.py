import json
from unittest.mock import patch

from django.test import TestCase

from agent.models import FunnelEvent
from catalog.models import Category, Product
from suppliers.models import Supplier

from .models import Order


class OrderCheckoutTests(TestCase):
    def setUp(self):
        supplier = Supplier.objects.create(channel_name="Test supplier")
        category = Category.objects.create(name="بانكيت", slug="بانكيت")
        self.product = Product.objects.create(
            supplier=supplier,
            category=category,
            title="بانكيت اختبار",
            slug="بانكيت-اختبار",
            color_options=["أوف وايت", "رمادي"],
            base_price=1000,
            commission_value=100,
        )

    @patch("orders.serializers.OrderSerializer._send_telegram_notification")
    def test_order_keeps_area_and_color_and_records_server_completion(self, _notify):
        response = self.client.post(
            "/api/orders/",
            data=json.dumps(
                {
                    "customer_name": "عميل اختبار",
                    "customer_phone": "01000000000",
                    "customer_governorate": "القاهرة",
                    "customer_area": "مدينة نصر",
                    "customer_address": "عنوان الاختبار",
                    "items": [
                        {
                            "product_id": str(self.product.id),
                            "quantity": 1,
                            "selected_color": "رمادي",
                        }
                    ],
                }
            ),
            content_type="application/json",
            HTTP_X_FURNITURE_VISITOR="visitor-test-123",
        )

        self.assertEqual(response.status_code, 201)
        order = Order.objects.get()
        self.assertEqual(order.customer_area, "مدينة نصر")
        self.assertEqual(order.items.get().selected_color, "رمادي")
        event = FunnelEvent.objects.get(order=order, event_type="order_complete")
        self.assertNotEqual(event.session_key, "visitor-test-123")
        self.assertTrue(event.session_key)

    def test_public_tracking_cannot_create_completed_order_event(self):
        response = self.client.post(
            "/api/track-funnel-event/",
            data=json.dumps({"event_type": "order_complete"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(FunnelEvent.objects.filter(event_type="order_complete").exists())
