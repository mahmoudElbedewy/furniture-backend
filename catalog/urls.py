from django.urls import path
from . import views

urlpatterns = [
    path("categories/", views.CategoryListView.as_view(), name="category-list"),
    path("filter-options/", views.CatalogFilterOptionsView.as_view(), name="catalog-filter-options"),
    path("search-suggestions/", views.CatalogSearchSuggestionsView.as_view(), name="catalog-search-suggestions"),
    path("products/", views.ProductListView.as_view(), name="product-list"),
    path(
        "products/id/<uuid:pk>/",
        views.ProductByIdDetailView.as_view(),
        name="product-detail-by-id",
    ),
    path(
        "products/<str:slug>/recommendations/",
        views.ProductRecommendationsView.as_view(),
        name="product-recommendations",
    ),
    path(
        "products/<str:slug>/", views.ProductDetailView.as_view(), name="product-detail"
    ),
    path(
        "products/<str:slug>/reviews/",
        views.ProductReviewListCreateView.as_view(),
        name="product-reviews",
    ),
    path("product-cards/", views.product_cards_api, name="product_cards_api"),
    path("favorites/", views.FavoriteListView.as_view(), name="favorite-list"),
    path(
        "favorites/toggle/", views.FavoriteToggleView.as_view(), name="favorite-toggle"
    ),
    path("favorites/check/", views.FavoriteCheckView.as_view(), name="favorite-check"),
]
