from django.core import signing

IDENTITY_SALT = "ha-furniture-guest-identity-v1"
MAX_AGE_SECONDS = 60 * 60 * 24 * 90 


def issue_identity_token(identifier: str) -> str:
    return signing.dumps({"cid": identifier}, salt=IDENTITY_SALT)


def verify_identity_token(token: str):
    """يرجّع الـ identifier لو التوكن صحيح وموقّع من السيرفر ومش منتهي، وإلا None."""
    if not token:
        return None
    try:
        data = signing.loads(token, salt=IDENTITY_SALT, max_age=MAX_AGE_SECONDS)
        return data.get("cid")
    except signing.SignatureExpired:
        return None
    except signing.BadSignature:
        return None


def resolve_identifier_for_request(request, data=None):
    """معرّف موثوق: JWT للمسجّلين، identity_token الموقّع للزوار.
    مفيش أي مصدر تاني مسموح — العميل مايقدرش يخترع identifier حد تاني."""
    if request.user.is_authenticated:
        email = (request.user.email or "").strip().lower()
        if email and "@" in email:
            return email.split("@")[0]
        return str(request.user.id)

    payload = data if data is not None else getattr(request, "data", {})
    token = payload.get("identity_token")
    return verify_identity_token(token) if token else None