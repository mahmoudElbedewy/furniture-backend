import uuid

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from suppliers.models import Supplier

from .models import Category, Product

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


class CatalogApiTests(TestCase):
    def setUp(self):
        self.supplier = Supplier.objects.create(channel_name="Test supplier")
        self.benches = Category.objects.create(name="بانكيت", slug="بانكيت")
        self.tables = Category.objects.create(
            name="ترابيزات انتريه",
            slug="ترابيزات-انتريه",
        )
        self.product = Product.objects.create(
            supplier=self.supplier,
            category=self.benches,
            title="بانكيت سحارة",
            slug="بانكيت-سحارة",
            description="قطعة تخزين للمنزل",
            material="قماش",
            color="أوف وايت",
            color_options=["أوف وايت", "أزرق بترولي"],
            base_price=1000,
            commission_value=100,
        )

    def test_catalog_cards_only_return_data_needed_for_listing(self):
        response = self.client.get("/api/catalog/products/?page_size=16")

        self.assertEqual(response.status_code, 200)
        card = response.json()["results"][0]
        self.assertIn("images", card)
        self.assertEqual(card["category_slug"], self.benches.slug)
        self.assertNotIn("variants", card)
        self.assertNotIn("shipping_rates", card)
        self.assertNotIn("reviews", card)

    def test_search_matches_furniture_synonym(self):
        response = self.client.get("/api/catalog/products/?search=كنبه")

        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.json()["results"]}
        self.assertIn(str(self.product.id), ids)

    def test_catalog_color_filter_includes_selectable_colors(self):
        filtered = self.client.get("/api/catalog/products/?color=أزرق بترولي")
        options = self.client.get("/api/catalog/filter-options/")

        self.assertEqual(filtered.status_code, 200)
        self.assertIn(
            str(self.product.id),
            {item["id"] for item in filtered.json()["results"]},
        )
        self.assertIn("أزرق بترولي", options.json()["colors"])

    def test_product_details_include_the_announced_delivery_estimate(self):
        response = self.client.get(f"/api/catalog/products/{self.product.slug}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["shipping_summary"]["estimated_delivery"],
            "خلال أسبوع من تأكيد الطلب",
        )

    def test_recommendations_separate_similar_and_complementary_products(self):
        same_category = Product.objects.create(
            supplier=self.supplier,
            category=self.benches,
            title="بانكيت آخر",
            slug="بانكيت-اخر",
            base_price=900,
            commission_value=100,
        )
        complementary = Product.objects.create(
            supplier=self.supplier,
            category=self.tables,
            title="ترابيزة انتريه",
            slug="ترابيزة-انتريه",
            base_price=800,
            commission_value=100,
        )

        response = self.client.get(
            f"/api/catalog/products/{self.product.slug}/recommendations/"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(str(same_category.id), {item["id"] for item in payload["similar"]})
        self.assertIn(
            str(complementary.id),
            {item["id"] for item in payload["complementary"]},
        )
