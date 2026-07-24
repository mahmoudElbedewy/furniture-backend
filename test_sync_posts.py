import os, sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

import requests
from agent.models import AgentSettings, FacebookPostMetric

s = AgentSettings.load()
token = s.meta_access_token
page_id = s.fb_page_id

# Use the USER token directly (not page token from me/accounts)
r = requests.get(
    f'https://graph.facebook.com/v25.0/{page_id}/published_posts',
    params={
        'access_token': token,
        'fields': 'id,message,full_picture,permalink_url,created_time,likes.summary(true),comments.summary(true),shares',
        'limit': 25,
    },
    timeout=15
)

data = r.json()
if 'error' in data:
    print('User token also failed:', data['error']['message'][:100])
    
    # Try with page token from me/accounts but using v19.0
    r2 = requests.get(
        f'https://graph.facebook.com/v19.0/{page_id}/published_posts',
        params={
            'access_token': token,
            'fields': 'id,message,full_picture,permalink_url,created_time',
            'limit': 25,
        },
        timeout=15
    )
    data2 = r2.json()
    if 'error' in data2:
        print('v19.0 also failed:', data2['error']['message'][:100])
    else:
        print(f'v19.0 worked! Got {len(data2.get("data", []))} posts')
else:
    print(f'Got {len(data.get("data", []))} posts with user token')
    posts_data = data['data']
    
    synced = 0
    for p in posts_data:
        try:
            obj, created = FacebookPostMetric.objects.update_or_create(
                post_id=p['id'],
                defaults={
                    'message': (p.get('message') or '')[:2000],
                    'image_url': p.get('full_picture', '') or '',
                    'permalink_url': p.get('permalink_url', '') or '',
                    'utm_campaign': f"post_{p['id']}",
                    'reach': 0,
                    'impressions': 0,
                    'likes': p.get('likes', {}).get('summary', {}).get('total_count', 0),
                    'comments': p.get('comments', {}).get('summary', {}).get('total_count', 0),
                    'shares': p.get('shares', {}).get('count', 0) if p.get('shares') else 0,
                    'clicks': 0,
                    'video_views': 0,
                    'post_type': 'photo' if p.get('full_picture') else 'status',
                    'engagement_rate': 0.0,
                    'published_at': p.get('created_time'),
                }
            )
            synced += 1
        except Exception as e:
            print(f'Error: {e}')
    
    print(f'Synced {synced} posts. Total in DB: {FacebookPostMetric.objects.count()}')
