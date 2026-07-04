import requests
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from asgiref.sync import async_to_sync
from agent.admin_agent import get_admin_reply
from telegram_bot.handlers import handle_order_approval, handle_order_rejection
from telegram_bot.agent_handlers import handle_agent_action_approval, handle_agent_action_rejection


def _send_telegram_message(base_url, chat_id, text):
    requests.post(
        f"{base_url}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": text,
        },
        timeout=15,
    )


def _get_telegram_file_url(base_url, file_id):
    response = requests.get(
        f"{base_url}/getFile",
        params={"file_id": file_id},
        timeout=15,
    )
    data = response.json()
    file_path = data.get("result", {}).get("file_path")
    if not file_path:
        return None
    return f"{base_url.replace('api.telegram.org/bot', 'api.telegram.org/file/bot')}/{file_path}"

class TelegramWebhookView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        update = request.data
        token = settings.TELEGRAM_BOT_TOKEN
        base_url = f"https://api.telegram.org/bot{token}"

        callback_query = update.get("callback_query")
        if not callback_query:
            message = update.get("message") or {}
            chat_id = str(message.get("chat", {}).get("id", ""))
            if chat_id != str(settings.TELEGRAM_ADMIN_CHAT_ID):
                return Response({"status": "unauthorized"})

            text = message.get("caption") or message.get("text") or ""
            image_urls = []

            photos = message.get("photo") or []
            if photos:
                photo = photos[-1]
                url = _get_telegram_file_url(base_url, photo.get("file_id"))
                if url:
                    image_urls.append(url)

            document = message.get("document") or {}
            mime_type = document.get("mime_type", "")
            if document.get("file_id") and mime_type.startswith("image/"):
                url = _get_telegram_file_url(base_url, document.get("file_id"))
                if url:
                    image_urls.append(url)

            if not text and not image_urls:
                return Response({"status": "ok"})

            admin_text = text or (
                "أنا الأدمن. اقرأ صور المنتج المرسلة من تيليجرام، استخرج البيانات، "
                "ولو كافية جهز طلب إضافة منتج للموافقة."
            )
            reply = async_to_sync(get_admin_reply)(
                history_messages=[],
                admin_message=admin_text,
                image_urls=image_urls,
            )
            _send_telegram_message(base_url, chat_id, reply)
            return Response({"status": "processed"})

        callback_data = callback_query.get("data")
        callback_id = callback_query.get("id")
        
        message = callback_query.get("message")
        if not message:
            return Response({"status": "ok"})
            
        sender_chat_id = str(message.get("chat", {}).get("id"))

        if sender_chat_id != str(settings.TELEGRAM_ADMIN_CHAT_ID):
            requests.post(
                f"{base_url}/answerCallbackQuery",
                data={
                    "callback_query_id": callback_id,
                    "text": "غير مصرح",
                },
            )
            return Response({"status": "unauthorized"})

        if callback_data.startswith("order_approve:"):
            order_number = callback_data.split(":", 1)[1]
            result_text = handle_order_approval(order_number)

        elif callback_data.startswith("order_reject:"):
            order_number = callback_data.split(":", 1)[1]
            result_text = handle_order_rejection(order_number)
            
        elif callback_data.startswith("agent_approve:"):
            req_id = callback_data.split(":", 1)[1]
            result_text = handle_agent_action_approval(req_id)

        elif callback_data.startswith("agent_reject:"):
            req_id = callback_data.split(":", 1)[1]
            result_text = handle_agent_action_rejection(req_id)

        else:
            result_text = "أمر غير معروف"

        requests.post(
            f"{base_url}/answerCallbackQuery",
            data={
                "callback_query_id": callback_id,
                "text": result_text,
            },
        )

        requests.post(
            f"{base_url}/editMessageText",
            data={
                "chat_id": sender_chat_id,
                "message_id": message["message_id"],
                "text": message.get("text", "") + f"\n\n{result_text}",
            },
        )

        return Response({"status": "ok"})
