from django.shortcuts import render
import uuid
from .identity import issue_identity_token, verify_identity_token
from rest_framework.response import Response
from rest_framework import generics, permissions
from .serializers import UserSerializer, RegisterSerializer

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

class UserDetailView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user
    
class GuestIdentityView(generics.GenericAPIView):
    """بيدي أي زائر جديد identity_token موقّع من السيرفر، أو يجدّد
    التوكن القديم لو لسه صالح. الفرونت لازم يستخدم التوكن ده بدل ما
    يخترع customer_identifier من عنده."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.data.get("identity_token")
        identifier = verify_identity_token(token) if token else None
        if not identifier:
            identifier = f"guest_{uuid.uuid4().hex[:12]}"
        return Response(
            {"identifier": identifier, "identity_token": issue_identity_token(identifier)}
        )