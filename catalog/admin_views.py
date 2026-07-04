from rest_framework import viewsets
from accounts.permissions import IsAdminRole
from .models import Product, Category
from .serializers import ProductSerializer, CategorySerializer

class AdminProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAdminRole] 

class AdminCategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminRole]