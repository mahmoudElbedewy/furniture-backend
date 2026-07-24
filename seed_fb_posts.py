import os
import django
import random
from datetime import timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from agent.models import FacebookPostMetric

def seed_data():
    print("Seeding FacebookPostMetric safely...")
    FacebookPostMetric.objects.all().delete()
    
    now = timezone.now()
    captions = [
        "Check out our new luxury sofa collection! 🛋️✨ #Furniture #HomeDecor",
        "Minimalist wooden dining tables now available. 🪑 Upgrade your space.",
        "A bedroom makeover that inspires dreams. 🛏️🌙",
        "Sale alert! 20% off all living room sets this weekend only. 🏷️",
        "Customer showcase: How beautiful does this armchair look in Sarah's home? 😍",
        "Bringing nature indoors with our rustic collection. 🌿🪵"
    ]
    images = [
        "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1524758631624-e2822e304c36?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1505691938895-1758d7def511?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1540574163026-643ea20d043d?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1538688525198-9b88f6f53126?auto=format&fit=crop&w=800&q=80"
    ]

    for i in range(10):
        posted = now - timedelta(days=random.randint(1, 30))
        reach = random.randint(1000, 5000)
        likes = random.randint(50, 500)
        comments = random.randint(5, 50)
        shares = random.randint(1, 30)
        eng_rate = (likes + comments + shares) / max(1, reach) * 100

        try:
            FacebookPostMetric.objects.create(
                post_id=f"fb_post_{i}",
                message=random.choice(captions),
                image_url=random.choice(images),
                reach=reach,
                impressions=reach + random.randint(100, 1000),
                likes=likes,
                comments=comments,
                shares=shares,
                post_type=random.choice(['photo', 'video', 'status']),
                engagement_rate=eng_rate,
                published_at=posted
            )
            print(f"Inserted fb_post_{i}")
        except Exception as e:
            print(f"Error inserting fb_post_{i}: {e}")

    print("Total after insert:", FacebookPostMetric.objects.count())

if __name__ == '__main__':
    seed_data()
