from rest_framework.test import APITestCase

from .models import ChatConversation


class ChatBrowsingContextTests(APITestCase):
    def test_guest_chat_keeps_navigation_context_and_accepts_its_identity_token(self):
        home_context = {
            "current_page": "/",
            "page_type": "catalog",
            "recent_navigation": [{"current_page": "/", "page_type": "catalog"}],
        }
        start = self.client.post(
            "/api/chat/start/",
            {"customer_name": "Guest", "context": home_context},
            format="json",
        )

        self.assertEqual(start.status_code, 200)
        conversation_id = start.data["id"]
        identity_token = start.data["identity_token"]

        history = self.client.get(
            f"/api/chat/{conversation_id}/history/",
            {"identity_token": identity_token},
        )
        self.assertEqual(history.status_code, 200)

        product_context = {
            "current_page": "/product/sofa-set/",
            "page_type": "product",
            "product_id": "11111111-1111-1111-1111-111111111111",
            "product_slug": "sofa-set",
            "product_name": "Sofa Set",
            "category_name": "Living Room",
            "recent_navigation": [
                {"current_page": "/", "page_type": "catalog"},
                {
                    "current_page": "/product/sofa-set/",
                    "page_type": "product",
                    "product_id": "11111111-1111-1111-1111-111111111111",
                    "product_name": "Sofa Set",
                },
            ],
        }
        updated = self.client.post(
            f"/api/chat/{conversation_id}/context/",
            {"identity_token": identity_token, "context": product_context},
            format="json",
        )

        self.assertEqual(updated.status_code, 200)
        conversation = ChatConversation.objects.get(id=conversation_id)
        self.assertEqual(conversation.last_page_context["current_page"], "/product/sofa-set/")
        self.assertEqual(conversation.last_page_context["product_name"], "Sofa Set")
        self.assertEqual(
            [event["current_page"] for event in conversation.page_history],
            ["/", "/product/sofa-set/"],
        )
