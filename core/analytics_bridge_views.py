import hmac
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from agent.analytics_sync import sync_all


@csrf_exempt
@require_http_methods(["POST"])
def trigger_sync(request):
    provided = request.headers.get("X-Bridge-Secret", "")
    if not hmac.compare_digest(provided, settings.TELEGRAM_BRIDGE_SECRET or ""):
        return JsonResponse({"error": "unauthorized"}, status=401)
    results = sync_all()
    return JsonResponse({"results": results})