from django.test import SimpleTestCase

from .views import CATEGORY_SLUG_PRIORITY, StandardResultsSetPagination


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
