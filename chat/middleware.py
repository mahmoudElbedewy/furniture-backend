from channels.middleware import BaseMiddleware
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model
from django.db import close_old_connections
from asgiref.sync import sync_to_async
from django.contrib.auth.models import AnonymousUser
import jwt
from django.conf import settings

User = get_user_model()

@sync_to_async
def get_user(validated_token):
    try:
        return User.objects.get(id=validated_token["user_id"])
    except User.DoesNotExist:
        return AnonymousUser()

class JwtAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        close_old_connections()
        
        # Extract token from query string (e.g. ws://...?token=xxxx)
        query_string = scope.get("query_string", b"").decode("utf-8")
        token = None
        for param in query_string.split("&"):
            if param.startswith("token="):
                token = param.split("=")[1]
                break

        if token:
            try:
                UntypedToken(token)
                decoded_data = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                scope["user"] = await get_user(decoded_data)
            except (InvalidToken, TokenError, jwt.DecodeError, Exception):
                scope["user"] = AnonymousUser()
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)
