import json
import random
import string
import uuid
from locust import HttpUser, task, between


def _pick_safe_products(products):
    safe = [
        p for p in products
        if not p.get("requires_deposit")
    ]
    return safe or products


class FurnitureShopper(HttpUser):
    wait_time = between(1, 4)

    def on_start(self):
        self.categories = []
        self.products = []

        resp = self.client.get("/api/catalog/categories/", name="/api/catalog/categories/")
        if resp.status_code == 200:
            try:
                self.categories = resp.json()
            except ValueError:
                print(f"⚠️ استجابة غير صالحة من /categories/: {resp.status_code} - {resp.text[:150]}")
        else:
            print(f"⚠️ فشل جلب التصنيفات: {resp.status_code} - {resp.text[:150]}")

        resp = self.client.get("/api/catalog/products/", name="/api/catalog/products/")
        if resp.status_code == 200:
            try:
                data = resp.json()
                self.products = data.get("results", data) if isinstance(data, dict) else data
                self.products = _pick_safe_products(self.products)
            except ValueError:
                print(f"⚠️ استجابة غير صالحة من /products/: {resp.status_code} - {resp.text[:150]}")
        else:
            print(f"⚠️ فشل جلب المنتجات: {resp.status_code} - {resp.text[:150]}")

    @task(6)
    def browse_products(self):
        params = {}
        if self.categories and random.random() < 0.4:
            cat = random.choice(self.categories)
            params["category"] = cat.get("slug")
        self.client.get("/api/catalog/products/", params=params, name="/api/catalog/products/ [browse]")

    @task(4)
    def view_product_detail(self):
        if not self.products:
            return
        product = random.choice(self.products)
        slug = product.get("slug")
        if slug:
            self.client.get(f"/api/catalog/products/{slug}/", name="/api/catalog/products/[slug]/")

    @task(2)
    def view_categories(self):
        self.client.get("/api/catalog/categories/", name="/api/catalog/categories/")

    @task(1)
    def create_fake_order(self):
        if not self.products:
            return

        product = random.choice(self.products)
        fake_id = uuid.uuid4().hex[:6]

        payload = {
            "customer_name": f"LoadTest User {fake_id}",
            "customer_phone": "0100" + "".join(random.choices(string.digits, k=7)),
            "customer_governorate": random.choice(
                ["القاهرة", "الجيزة", "الإسكندرية", "الدقهلية"]
            ),
            "customer_address": f"عنوان تجريبي {fake_id} - اختبار حمل",
            "notes": "LOADTEST",
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": 1,
                }
            ],
        }

        with self.client.post(
            "/api/orders/",
            json=payload,
            name="/api/orders/ [create]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 400 and "variant_id" in resp.text:
                resp.success()
            elif resp.status_code not in (200, 201):
                resp.failure(f"unexpected status {resp.status_code}: {resp.text[:200]}")

    @task(1)
    def track_random_order_should_fail(self):
        fake_order_number = "ORD-" + "".join(random.choices("0123456789ABCDEF", k=8))
        self.client.get(
            f"/api/orders/track/{fake_order_number}/",
            name="/api/orders/track/[order_number]/",
        )