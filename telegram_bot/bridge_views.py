from telegram_bot.agent_handlers import handle_agent_action_approval, handle_agent_action_rejection
import json
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import AdminNotification, TelegramBridgeState
from .handlers import handle_order_approval, handle_order_rejection
import hmac


def _check_secret(request):
    provided = request.headers.get("X-Bridge-Secret", "")
    expected = settings.TELEGRAM_BRIDGE_SECRET or ""
    return hmac.compare_digest(provided, expected)

@require_http_methods(["GET"])
def pending_notifications(request):
    if not _check_secret(request):
        return JsonResponse({"error": "unauthorized"}, status=401)

    items = AdminNotification.objects.filter(sent_via_telegram=False).order_by("id")[:20]
    results = [
        {
            "id": n.id,
            "message": n.message,
            "buttons": n.buttons or [],
        }
        for n in items
    ]
    return JsonResponse({"results": results})


@csrf_exempt
@require_http_methods(["POST"])
def mark_sent(request, notification_id):
    if not _check_secret(request):
        return JsonResponse({"error": "unauthorized"}, status=401)

    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        data = {}

    try:
        notification = AdminNotification.objects.get(id=notification_id)
    except AdminNotification.DoesNotExist:
        return JsonResponse({"error": "not found"}, status=404)

    notification.sent_via_telegram = bool(data.get("sent", True))
    notification.save(update_fields=["sent_via_telegram"])
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def offset_view(request):
    if not _check_secret(request):
        return JsonResponse({"error": "unauthorized"}, status=401)

    state, _ = TelegramBridgeState.objects.get_or_create(key="last_offset", defaults={"value": ""})

    if request.method == "GET":
        offset = int(state.value) if state.value else None
        return JsonResponse({"offset": offset})

    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        data = {}
    state.value = str(data.get("offset", ""))
    state.save(update_fields=["value"])
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
def approve_order(request, order_number):
    if not _check_secret(request):
        return JsonResponse({"error": "unauthorized"}, status=401)
    result = handle_order_approval(order_number)
    return JsonResponse({"result": result})


@csrf_exempt
@require_http_methods(["POST"])
def reject_order(request, order_number):
    if not _check_secret(request):
        return JsonResponse({"error": "unauthorized"}, status=401)
    result = handle_order_rejection(order_number)
    return JsonResponse({"result": result})



@csrf_exempt
@require_http_methods(["POST"])
def approve_agent_action(request, req_id):
    if not _check_secret(request):
        return JsonResponse({"error": "unauthorized"}, status=401)
    result = handle_agent_action_approval(req_id)
    return JsonResponse({"result": result})


@csrf_exempt
@require_http_methods(["POST"])
def reject_agent_action(request, req_id):
    if not _check_secret(request):
        return JsonResponse({"error": "unauthorized"}, status=401)
    result = handle_agent_action_rejection(req_id)
    return JsonResponse({"result": result})