from rest_framework import generics, permissions
from django.db.models import Q
from .models import Order
from .serializers import OrderSerializer

class OrderCreateView(generics.CreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [permissions.AllowAny]

class OrderTrackView(generics.RetrieveAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'order_number'


class MyOrdersView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        query = Q(user=user)
        if getattr(user, 'phone_number', ''):
            query |= Q(customer_phone=user.phone_number)
        return Order.objects.filter(query).distinct().order_by('-created_at')


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import AbandonedCart
from catalog.models import Product

class AbandonedCartCreateView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        phone_number = request.data.get('phone_number')
        product_id = request.data.get('product_id')

        if not phone_number or not product_id:
            return Response({"error": "phone_number and product_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            product = Product.objects.get(id=product_id, is_available=True)
            AbandonedCart.objects.create(phone_number=phone_number, product=product)
            return Response({"message": "Abandoned cart recorded"}, status=status.HTTP_201_CREATED)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
