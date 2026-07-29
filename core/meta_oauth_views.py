import requests
from datetime import timedelta
from urllib.parse import urlencode, quote

from django.conf import settings
from django.core import signing
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import views, permissions
from rest_framework.response import Response

from accounts.permissions import IsAdminRole
from agent.models import AgentSettings

GRAPH_API_VERSION = "v19.0"
OAUTH_STATE_SALT = "ha-furniture-meta-oauth-state-v1"
OAUTH_STATE_MAX_AGE = 60 * 10 


def _issue_oauth_state(admin_user_id) -> str:
    return signing.dumps({"uid": str(admin_user_id)}, salt=OAUTH_STATE_SALT)


def _verify_oauth_state(state: str):
    if not state:
        return None
    try:
        data = signing.loads(state, salt=OAUTH_STATE_SALT, max_age=OAUTH_STATE_MAX_AGE)
        return data.get("uid")
    except (signing.BadSignature, signing.SignatureExpired):
        return None


def _redirect_uri() -> str:
    return f"{settings.BACKEND_BASE_URL}/api/meta/oauth/callback/"


def _settings_redirect(status: str, reason: str = "") -> str:
    params = {"meta_oauth": status}
    if reason:
        params["reason"] = reason[:150]
    return f"{settings.FRONTEND_BASE_URL}/?{urlencode(params)}#analytics"


class MetaOAuthStartView(views.APIView):
    """
    محمي بصلاحية الأدمن. بيرجع رابط OAuth dialog بتاع فيسبوك عشان
    الفرونت يعمل redirect كامل عليه (مش fetch عادي).
    """

    permission_classes = [IsAdminRole]

    def get(self, request):
        if not settings.FACEBOOK_APP_ID:
            return Response(
                {"error": "FACEBOOK_APP_ID غير مضبوط في إعدادات السيرفر."}, status=400
            )

        state = _issue_oauth_state(request.user.id)
        params = {
            "client_id": settings.FACEBOOK_APP_ID,
            "redirect_uri": _redirect_uri(),
            "state": state,
            "scope": settings.META_OAUTH_SCOPES,
            "response_type": "code",
        }
        oauth_url = f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth?{urlencode(params)}"
        return Response({"oauth_url": oauth_url})


class MetaOAuthCallbackView(views.APIView):
    """
    Public endpoint — بيستقبل الـ redirect من فيسبوك مباشرة بعد موافقة
    الأدمن، فمينفعش يتحمي بـ JWT. الحماية الوحيدة هي التحقق من الـ
    state الموقّع (نفس نمط accounts/identity.py) اللي بيثبت إن الطلب
    فعلاً بدأ من MetaOAuthStartView خلال آخر 10 دقايق.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        error = request.query_params.get("error")
        if error:
            return redirect(_settings_redirect("error", error))

        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or not _verify_oauth_state(state):
            return redirect(_settings_redirect("error", "invalid_or_expired_state"))

        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(max_retries=2)
        session.mount("https://", adapter)
        _timeout = 30

        try:
            token_resp = session.get(
                f"https://graph.facebook.com/{GRAPH_API_VERSION}/oauth/access_token",
                params={
                    "client_id": settings.FACEBOOK_APP_ID,
                    "client_secret": settings.FACEBOOK_APP_SECRET,
                    "redirect_uri": _redirect_uri(),
                    "code": code,
                },
                timeout=_timeout,
            )
            token_data = token_resp.json()
            short_lived_token = token_data.get("access_token")
            if not short_lived_token:
                msg = token_data.get("error", {}).get("message", "لم يتم استلام access_token")
                return redirect(_settings_redirect("error", msg))

            long_resp = session.get(
                f"https://graph.facebook.com/{GRAPH_API_VERSION}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": settings.FACEBOOK_APP_ID,
                    "client_secret": settings.FACEBOOK_APP_SECRET,
                    "fb_exchange_token": short_lived_token,
                },
                timeout=_timeout,
            )
            long_data = long_resp.json()
            long_lived_token = long_data.get("access_token", short_lived_token)
            expires_in = long_data.get("expires_in")

            pages_resp = session.get(
                f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/accounts",
                params={"access_token": long_lived_token, "fields": "id,name,access_token"},
                timeout=_timeout,
            )
            pages_data = pages_resp.json()
            pages = pages_data.get("data", [])
            if not pages:
                return redirect(_settings_redirect("error", "no_facebook_pages_found"))

            agent_settings = AgentSettings.load()

            selected_page = None
            if agent_settings.fb_page_id:
                selected_page = next(
                    (p for p in pages if str(p.get("id")) == str(agent_settings.fb_page_id)),
                    None,
                )
            if not selected_page:
                selected_page = pages[0]

            agent_settings.meta_access_token = selected_page.get("access_token", long_lived_token)
            agent_settings.fb_page_id = str(selected_page.get("id", agent_settings.fb_page_id))
            agent_settings.is_meta_connected = True
            agent_settings.meta_token_expires_at = (
                timezone.now() + timedelta(seconds=int(expires_in)) if expires_in else None
            )
            agent_settings.save(
                update_fields=[
                    "meta_access_token",
                    "fb_page_id",
                    "is_meta_connected",
                    "meta_token_expires_at",
                ]
            )

            # Trigger sync immediately
            try:
                from agent.analytics_sync import sync_facebook
                sync_facebook(agent_settings)
            except Exception:
                pass

            return redirect(_settings_redirect("success"))
        except requests.RequestException as exc:
            return redirect(_settings_redirect("error", str(exc)[:100]))