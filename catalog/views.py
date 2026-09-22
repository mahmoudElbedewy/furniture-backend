from rest_framework import generics, permissions
from .serializers import (
    CategorySerializer,
    ProductCardSerializer,
    ProductSerializer,
    ReviewSerializer,
    FavoriteSerializer,
)
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from orders.models import OrderItem
from accounts.identity import resolve_identifier_for_request
import uuid

from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.db.models import Case, F, IntegerField, Prefetch, Q, Value, When
from .models import (
    Category,
    Product,
    Review,
    Favorite,
    SearchQuery,
    ProductShippingRate,
)


CATEGORY_SLUG_PRIORITY = (
    "بانكيت",
    "دولاب",
    "ترابيزات-انتريه",
    "ترابيزات-الشاشة",
    "مكتبات",
)

SEARCH_SYNONYMS = {
    "كنبة": ("كنبة", "كنبه", "بانكيت", "سحارة"),
    "كنبه": ("كنبة", "كنبه", "بانكيت", "سحارة"),
    "سحارة": ("سحارة", "بانكيت"),
    "سحاره": ("سحارة", "سحاره", "بانكيت"),
    "خزانة": ("خزانة", "دولاب"),
    "خزانه": ("خزانة", "خزانه", "دولاب"),
    "دولاب": ("دولاب", "خزانة"),
    "ترابيزة": ("ترابيزة", "ترابيزات"),
    "ترابيزه": ("ترابيزة", "ترابيزات"),
    "طاولة": ("طاولة", "ترابيزة", "ترابيزات"),
    "مكتب": ("مكتب", "مكاتب"),
}

COMPLEMENTARY_CATEGORY_SLUGS = {
    "بانكيت": ("ترابيزات-انتريه", "ترابيزات-الشاشة", "مكتبات"),
    "دولاب": ("مكاتب", "مكتبات", "ترابيزات-الشاشة"),
    "ترابيزات-انتريه": ("بانكيت", "مكتبات"),
    "ترابيزات-الشاشة": ("بانكيت", "مكتبات"),
    "مكتبات": ("ترابيزات-انتريه", "ترابيزات-الشاشة", "مكاتب"),
    "مكاتب": ("مكتبات", "دولاب"),
}


def search_terms(value):
    query = " ".join((value or "").strip().lower().split())
    if not query:
        return []

    return [
        tuple(dict.fromkeys(SEARCH_SYNONYMS.get(token, (token,))))
        for token in query.split()
    ]


def text_match_query(term):
    return (
        Q(title__icontains=term)
        | Q(description__icontains=term)
        | Q(material__icontains=term)
        | Q(color__icontains=term)
        | Q(dimensions__icontains=term)
        | Q(category__name__icontains=term)
    )


def product_search_query(value):
    query = Q()
    for alternatives in search_terms(value):
        alternatives_query = Q()
        for term in alternatives:
            alternatives_query |= text_match_query(term)
        query &= alternatives_query
    return query


def category_priority_expression(field_name):
    return Case(
        *[
            When(**{field_name: slug}, then=Value(priority))
            for priority, slug in enumerate(CATEGORY_SLUG_PRIORITY)
        ],
        default=Value(len(CATEGORY_SLUG_PRIORITY)),
        output_field=IntegerField(),
    )


def product_cards_api(request):
    ids_param = request.GET.get("ids", "")
    if not ids_param:
        return JsonResponse({"products": []})

    raw_ids = [raw.strip() for raw in ids_param.split(",") if raw.strip()]

    valid_ids = []
    for raw_id in raw_ids:
        try:
            valid_ids.append(uuid.UUID(raw_id))
        except (ValueError, AttributeError, TypeError):
            continue

    if not valid_ids:
        return JsonResponse({"products": []})

    products = Product.objects.filter(
        id__in=valid_ids, is_available=True
    ).prefetch_related("images")

    data = []
    for p in products:
        data.append(
            {
                "id": str(p.id),
                "title": p.title,
                "final_price": float(p.final_price),
                "requires_deposit": p.requires_deposit,
                "deposit_amount": float(p.deposit_amount) if p.deposit_amount else None,
                "image_url": p.primary_image_url(),
                "slug": p.slug,
            }
        )

    return JsonResponse({"products": data})




class StandardResultsSetPagination(PageNumberPagination):
    page_size = 16
    page_size_query_param = "page_size"
    max_page_size = 100


class CategoryListView(generics.ListAPIView):
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Category.objects.annotate(
            display_priority=category_priority_expression("slug")
        ).order_by("display_priority", "name")


class ProductListView(generics.ListAPIView):
    serializer_class = ProductCardSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = StandardResultsSetPagination

    def _log_search_query(self, search, qs):
        search_text = (search or "").strip()
        if not search_text:
            return

        results_count = qs.count()
        params = self.request.query_params
        tracked_filters = {
            key: params.get(key)
            for key in (
                "category",
                "min_price",
                "max_price",
                "material",
                "color",
                "dimensions",
                "has_deposit",
                "ships_nationwide",
                "ordering",
            )
            if params.get(key) not in (None, "")
        }

        SearchQuery.objects.create(
            query=search_text[:255],
            normalized_query=" ".join(search_text.lower().split())[:255],
            results_count=results_count,
            has_results=results_count > 0,
            customer_identifier=resolve_identifier_for_request(self.request, params) or "",
            user=self.request.user if self.request.user.is_authenticated else None,
            filters=tracked_filters,
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        self._log_search_query(request.query_params.get("search"), queryset)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        qs = (
            Product.objects.filter(is_available=True)
            .select_related("category")
            # Catalog cards need one image and a few labels. Details such as
            # variants, shipping, and reviews are loaded only on the PDP.
            .prefetch_related("images")
        )
        params = self.request.query_params

        search = params.get("search")
        if search:
            qs = qs.filter(product_search_query(search))

        category = params.get("category")
        if category:
            qs = qs.filter(category__slug=category)

        min_price = params.get("min_price")
        max_price = params.get("max_price")
        if min_price:
            qs = qs.filter(final_price__gte=min_price)
        if max_price:
            qs = qs.filter(final_price__lte=max_price)

        material = params.get("material")
        if material:
            qs = qs.filter(material__icontains=material)

        color = params.get("color")
        if color:
            qs = qs.filter(
                Q(color__icontains=color) | Q(color_options__contains=[color])
            )

        dimensions = params.get("dimensions")
        if dimensions:
            qs = qs.filter(dimensions__icontains=dimensions)

        has_deposit = params.get("has_deposit")
        if has_deposit is not None:
            if has_deposit.lower() in ("true", "1", "yes"):
                qs = qs.filter(requires_deposit=True)
            elif has_deposit.lower() in ("false", "0", "no"):
                qs = qs.filter(requires_deposit=False)

        ships_nationwide = params.get("ships_nationwide")
        if ships_nationwide is not None:
            if ships_nationwide.lower() in ("true", "1", "yes"):
                qs = qs.filter(ships_nationwide=True)
            elif ships_nationwide.lower() in ("false", "0", "no"):
                qs = qs.filter(ships_nationwide=False)

        ordering = params.get("ordering")
        if ordering in (
            "final_price",
            "-final_price",
            "created_at",
            "-created_at",
            "orders_count",
            "-orders_count",
        ):
            qs = qs.order_by(ordering)
        else:
            qs = qs.annotate(
                category_priority=category_priority_expression("category__slug")
            ).order_by("category_priority", "-created_at")

        return qs


class CatalogFilterOptionsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        products = Product.objects.filter(is_available=True)
        base_colors = (
            products.exclude(color__isnull=True)
            .exclude(color__exact="")
            .values_list("color", flat=True)
            .distinct()
        )
        selectable_colors = set()
        for color in base_colors:
            selectable_colors.add(color)
        for options in products.exclude(color_options__exact=[]).values_list(
            "color_options", flat=True
        ):
            if isinstance(options, list):
                selectable_colors.update(
                    str(color).strip() for color in options if str(color).strip()
                )
        materials = (
            products.exclude(material__isnull=True)
            .exclude(material__exact="")
            .values_list("material", flat=True)
            .distinct()
            .order_by("material")[:50]
        )
        return Response(
            {
                "colors": sorted(selectable_colors)[:50],
                "materials": list(materials),
            }
        )


class CatalogSearchSuggestionsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if len(query) < 2:
            return Response({"products": [], "categories": []})

        products = (
            Product.objects.filter(is_available=True)
            .filter(product_search_query(query))
            .select_related("category")
            .prefetch_related("images")
            .order_by("-orders_count", "-views_count", "-created_at")[:6]
        )
        categories = (
            Category.objects.filter(Q(name__icontains=query) | Q(slug__icontains=query))
            .annotate(display_priority=category_priority_expression("slug"))
            .order_by("display_priority", "name")[:4]
        )
        return Response(
            {
                "products": ProductCardSerializer(products, many=True).data,
                "categories": CategorySerializer(categories, many=True).data,
            }
        )


class ProductDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.filter(is_available=True)
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("category")
            .prefetch_related(
                "images",
                "variants",
                Prefetch("reviews", queryset=Review.objects.order_by("-created_at")),
                Prefetch(
                    "shipping_rates",
                    queryset=ProductShippingRate.objects.select_related(
                        "governorate", "area"
                    ),
                ),
            )
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        Product.objects.filter(pk=instance.pk).update(
            views_count=F("views_count") + 1
        )
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class ProductByIdDetailView(ProductDetailView):
    """Serve a product through its stable identifier for shared links."""

    lookup_field = "pk"


class ProductRecommendationsView(APIView):
    """Keep alternative and complementary browsing below the purchase decision."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        product = get_object_or_404(Product, slug=slug, is_available=True)
        base = (
            Product.objects.filter(is_available=True)
            .exclude(pk=product.pk)
            .select_related("category")
            .prefetch_related("images")
            .order_by("-orders_count", "-views_count", "-created_at")
        )
        similar = list(base.filter(category=product.category)[:10])
        complementary_slugs = COMPLEMENTARY_CATEGORY_SLUGS.get(
            product.category.slug,
            (),
        )
        complementary = list(
            base.filter(category__slug__in=complementary_slugs)
            .exclude(pk__in=[item.pk for item in similar])[:6]
        )
        if not complementary:
            complementary = list(
                base.exclude(pk__in=[item.pk for item in similar])[:6]
            )
        return Response(
            {
                "similar": ProductCardSerializer(similar, many=True).data,
                "complementary": ProductCardSerializer(complementary, many=True).data,
            }
        )





class ProductReviewListCreateView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        product = get_object_or_404(Product, slug=slug, is_available=True)
        reviews = product.reviews.all().order_by("-created_at")
        serializer = ReviewSerializer(reviews, many=True)
        return Response(serializer.data)

    def post(self, request, slug):
        product = get_object_or_404(Product, slug=slug, is_available=True)

        is_verified_purchase = False
        customer_name = request.data.get("customer_name")

        if request.user.is_authenticated:
            if not customer_name:
                customer_name = (
                    request.user.full_name or request.user.email.split("@")[0]
                )

            has_purchased = OrderItem.objects.filter(
                order__user=request.user, product=product, order__status="delivered"
            ).exists()
            if has_purchased:
                is_verified_purchase = True

        if not customer_name:
            customer_name = "مجهول"

        data = {
            "customer_name": customer_name,
            "rating": request.data.get("rating"),
            "comment": request.data.get("comment"),
            "is_verified_purchase": is_verified_purchase,
        }

        serializer = ReviewSerializer(data=data)
        if serializer.is_valid():
            serializer.save(product=product)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class FavoriteListView(generics.ListAPIView):
    serializer_class = FavoriteSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        customer_identifier = resolve_identifier_for_request(self.request, self.request.query_params)
        if not customer_identifier:
            return Favorite.objects.none()
        return (
            Favorite.objects.filter(customer_identifier=customer_identifier)
            .select_related("product")
            .order_by("-created_at")
        )


class FavoriteToggleView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        product_id = request.data.get("product_id")
        customer_identifier = resolve_identifier_for_request(request)

        if not product_id or not customer_identifier:
            return Response(
                {"error": "product_id مطلوب و identity_token غير صالح"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            product = Product.objects.get(id=product_id, is_available=True)
        except (Product.DoesNotExist, ValueError, ValidationError):
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        favorite, created = Favorite.objects.get_or_create(
            product=product, customer_identifier=customer_identifier
        )
        if created:
            return Response(FavoriteSerializer(favorite).data, status=status.HTTP_201_CREATED)
        favorite.delete()
        return Response({"message": "Removed from favorites"}, status=status.HTTP_200_OK)


class FavoriteCheckView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        product_id = request.query_params.get("product_id")
        customer_identifier = resolve_identifier_for_request(request, request.query_params)
        if not product_id or not customer_identifier:
            return Response({"is_favorited": False}, status=status.HTTP_200_OK)
        is_favorited = Favorite.objects.filter(
            product_id=product_id, customer_identifier=customer_identifier
        ).exists()
        return Response({"is_favorited": is_favorited}, status=status.HTTP_200_OK)
