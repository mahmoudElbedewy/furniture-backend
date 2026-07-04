import time
import ssl
import requests
from requests.adapters import HTTPAdapter
from django.core.management.base import BaseCommand
from django.conf import settings
from telegram_bot.handlers import handle_order_approval, handle_order_rejection


class _EOFTolerantAdapter(HTTPAdapter):
    """
    يحل مشكلة SSLEOFError (UNEXPECTED_EOF_WHILE_READING) المعروفة بين
    Python 3.10/3.11 + urllib3 2.x + OpenSSL 3.0، عن طريق تفعيل
    SSL_OP_IGNORE_UNEXPECTED_EOF على الـ SSL context.
    """

    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        if hasattr(ssl, "OP_IGNORE_UNEXPECTED_EOF"):
            context.options |= ssl.OP_IGNORE_UNEXPECTED_EOF
        kwargs["ssl_context"] = context
        return super().init_poolmanager(*args, **kwargs)


_session = requests.Session()
_session.mount("https://", _EOFTolerantAdapter())


class Command(BaseCommand):
    help = "يشغّل بوت تليجرام في وضع Polling لاستقبال ضغطات أزرار الموافقة/الرفض"

    def _base_url(self):
        token = settings.TELEGRAM_BOT_TOKEN
        if settings.TELEGRAM_RELAY_BASE_URL:
            return f"{settings.TELEGRAM_RELAY_BASE_URL}/bot{token}"
        return f"https://api.telegram.org/bot{token}"

    def _relay_headers(self):
        if settings.TELEGRAM_RELAY_BASE_URL and settings.TELEGRAM_RELAY_SECRET:
            return {"X-Relay-Secret": settings.TELEGRAM_RELAY_SECRET}
        return {}

    def handle(self, *args, **options):
        base_url = self._base_url()
        headers = self._relay_headers()
        offset = None
        post_timeout = 15

        self.stdout.write(self.style.SUCCESS("بوت التليجرام شغال... (Polling)"))

        while True:
            try:
                params = {"timeout": 30}
                if offset:
                    params["offset"] = offset

                response = _session.get(
                    f"{base_url}/getUpdates",
                    params=params,
                    headers=headers,
                    timeout=(10, 40),
                )
                data = response.json()

                if not data.get("ok", False):
                    self.stdout.write(
                        self.style.WARNING(f"تليجرام رجّع خطأ: {data}")
                    )
                    time.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1

                    try:
                        self._process_update(update, base_url, headers, post_timeout)
                    except Exception as update_error:  # noqa: BLE001
                        self.stdout.write(
                            self.style.ERROR(
                                f"خطأ أثناء معالجة update {update.get('update_id')}: {update_error}"
                            )
                        )

            except requests.exceptions.ReadTimeout:
                # طبيعي جدًا في الـ long polling، مفيش تحديثات جديدة
                continue
            except requests.RequestException as e:
                self.stdout.write(self.style.WARNING(f"خطأ مؤقت في الاتصال: {e}"))
                time.sleep(5)
            except Exception as loop_error:  # noqa: BLE001
                self.stdout.write(
                    self.style.ERROR(f"خطأ غير متوقع في اللوب الرئيسي: {loop_error}")
                )
                time.sleep(5)

    def _process_update(self, update, base_url, headers, post_timeout):
        callback_query = update.get("callback_query")
        if not callback_query:
            return

        callback_data = callback_query["data"]
        callback_id = callback_query["id"]

        sender_chat_id = str(callback_query["message"]["chat"]["id"])
        if sender_chat_id != str(settings.TELEGRAM_ADMIN_CHAT_ID):
            _session.post(
                f"{base_url}/answerCallbackQuery",
                data={"callback_query_id": callback_id, "text": "غير مصرح"},
                headers=headers,
                timeout=post_timeout,
            )
            return

        if callback_data.startswith("order_approve:"):
            order_number = callback_data.split(":", 1)[1]
            result_text = handle_order_approval(order_number)

        elif callback_data.startswith("order_reject:"):
            order_number = callback_data.split(":", 1)[1]
            result_text = handle_order_rejection(order_number)

        elif callback_data.startswith("agent_approve:"):
            req_id = callback_data.split(":", 1)[1]
            from telegram_bot.agent_handlers import handle_agent_action_approval
            result_text = handle_agent_action_approval(req_id)

        elif callback_data.startswith("agent_reject:"):
            req_id = callback_data.split(":", 1)[1]
            from telegram_bot.agent_handlers import handle_agent_action_rejection
            result_text = handle_agent_action_rejection(req_id)

        else:
            result_text = "أمر غير معروف"

        _session.post(
            f"{base_url}/answerCallbackQuery",
            data={"callback_query_id": callback_id, "text": result_text},
            headers=headers,
            timeout=post_timeout,
        )

        _session.post(
            f"{base_url}/editMessageText",
            data={
                "chat_id": callback_query["message"]["chat"]["id"],
                "message_id": callback_query["message"]["message_id"],
                "text": callback_query["message"]["text"] + f"\n\n{result_text}",
            },
            headers=headers,
            timeout=post_timeout,
        )