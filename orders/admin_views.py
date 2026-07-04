from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from accounts.permissions import IsAdminRole
from .models import Order, OrderStatusLog
from .serializers import OrderSerializer


class AdminOrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsAdminRole]

    @action(detail=True, methods=["patch"])
    def status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get("status")
        if not new_status:
            return Response(
                {"error": "status required"}, status=status.HTTP_400_BAD_REQUEST
            )

        old_status = order.status

        # Use serializer update to handle commission status changes
        serializer = self.get_serializer(
            order, data={"status": new_status}, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        OrderStatusLog.objects.create(
            order=order,
            old_status=old_status,
            new_status=new_status,
            changed_by="admin",
        )
        return Response(serializer.data)
