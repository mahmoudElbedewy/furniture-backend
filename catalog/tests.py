import uuid

from django.test import SimpleTestCase
from django.urls import reverse

from .views import (
    CATEGORY_SLUG_PRIORITY,
    ProductByIdDetailView,
    StandardResultsSetPagination,
)


class CatalogPaginationTests(SimpleTestCase):
    def test_default_catalog_page_contains_sixteen_products(self):
        self.assertEqual(StandardResultsSetPagination.page_size, 16)

    def test_featured_category_order_matches_storefront_requirement(self):
        self.assertEqual(
            CATEGORY_SLUG_PRIORITY,
            (
                "بانكيت",
                "دولاب",
                "ترابيزات-انتريه",
                "ترابيزات-الشاشة",
                "مكتبات",
            ),
        )


class ProductShareLinkTests(SimpleTestCase):
    def test_product_can_be_resolved_by_stable_identifier(self):
        product_id = uuid.uuid4()

        self.assertEqual(
            reverse("product-detail-by-id", kwargs={"pk": product_id}),
            f"/api/catalog/products/id/{product_id}/",
        )
        self.assertEqual(ProductByIdDetailView.lookup_field, "pk")
