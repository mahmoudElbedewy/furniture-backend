import requests
from datetime import datetime
from django.utils import timezone
from .models import (
    AgentSettings, FacebookPostMetric, DailyMetricSnapshot,
    GACampaignSession, GADailyTraffic, GATopPage,
)

GRAPH_API_BASE = 'https://graph.facebook.com/v25.0'


def _graph_get(endpoint, token, params=None):
    params = {**(params or {}), 'access_token': token}
    try:
        r = requests.get(f'{GRAPH_API_BASE}/{endpoint}', params=params, timeout=15)
        data = r.json()
        if r.status_code == 200 and 'error' not in data:
            return data
        error = data.get('error', {}).get('message', f'HTTP {r.status_code}') if isinstance(data, dict) else f'HTTP {r.status_code}'
        return {'error': error}
    except requests.RequestException as exc:
        return {'error': str(exc)}


def sync_facebook(settings: AgentSettings):
    token = settings.meta_access_token
    page_id = settings.fb_page_id
    if not token or not page_id:
        return {'ok': False, 'error': 'Missing Meta token/page id'}

    # Resolve page token
    accounts = _graph_get('me/accounts', token)
    page_token = token
    if accounts and accounts.get('error'):
        settings.is_meta_connected = False
        settings.save(update_fields=['is_meta_connected'])
        return {'ok': False, 'error': accounts['error']}
    if accounts and 'data' in accounts:
        for page in accounts['data']:
            if str(page.get('id')) == str(page_id):
                page_token = page.get('access_token', token)
                break

    page_info = _graph_get(page_id, page_token, {'fields': 'name,followers_count,fan_count'})
    followers_count = None
    if page_info and page_info.get('error'):
        settings.is_meta_connected = False
        settings.save(update_fields=['is_meta_connected'])
        return {'ok': False, 'error': page_info['error']}
    if page_info:
        followers_count = page_info.get('followers_count')
        if followers_count is None:
            followers_count = page_info.get('fan_count')
        if followers_count is not None:
            settings.fb_followers_override = int(followers_count)

    posts = _graph_get(
        f'{page_id}/posts', page_token,
        {'fields': 'id,message,full_picture,permalink_url,created_time,'
                   'likes.summary(true),comments.summary(true),shares,'
                   'insights.metric(post_impressions,post_impressions_unique,post_clicks,post_video_views)',
         'limit': 25},
    )
    if not posts or posts.get('error'):
        posts = _graph_get(
            f'{page_id}/published_posts', page_token,
            {'fields': 'id,message,full_picture,permalink_url,created_time',
             'limit': 25},
        )

    synced_posts = 0
    if posts and 'data' in posts:
        for p in posts['data']:
            likes = p.get('likes', {}).get('summary', {}).get('total_count', 0)
            comments = p.get('comments', {}).get('summary', {}).get('total_count', 0)
            shares = p.get('shares', {}).get('count', 0) if p.get('shares') else 0

            insight_values = {i['name']: i['values'][0]['value']
                               for i in (p.get('insights', {}).get('data') or [])}
            reach = insight_values.get('post_impressions_unique', 0)
            impressions = insight_values.get('post_impressions', 0)
            clicks = insight_values.get('post_clicks', 0)
            video_views = insight_values.get('post_video_views', 0)

            link = p.get('permalink_url', '') or ''
            utm_campaign = ''
            if 'utm_campaign=' in link:
                utm_campaign = link.split('utm_campaign=')[1].split('&')[0]
            else:
                utm_campaign = f"post_{p['id']}"

            total_engagement = likes + comments + shares
            engagement_rate = round((total_engagement / reach) * 100, 2) if reach else 0.0

            FacebookPostMetric.objects.update_or_create(
                post_id=p['id'],
                defaults=dict(
                    message=(p.get('message') or '')[:2000],
                    image_url=(p.get('full_picture') or '')[:500],
                    permalink_url=link[:500],
                    utm_campaign=utm_campaign[:150],
                    reach=reach, impressions=impressions,
                    likes=likes, comments=comments, shares=shares,
                    clicks=clicks, video_views=video_views,
                    post_type='video' if video_views else ('photo' if p.get('full_picture') else 'status'),
                    engagement_rate=engagement_rate,
                    published_at=p.get('created_time'),
                ),
            )
            synced_posts += 1

    today = timezone.localdate()
    if followers_count is not None:
        DailyMetricSnapshot.objects.update_or_create(
            date=today, source='facebook', metric_name='followers',
            defaults={'value': int(followers_count)},
        )
    settings.last_meta_sync = timezone.now()
    settings.is_meta_connected = True
    update_fields = ['is_meta_connected', 'last_meta_sync']
    if followers_count is not None:
        update_fields.append('fb_followers_override')
    settings.save(update_fields=update_fields)
    return {'ok': True, 'posts_synced': synced_posts}


def sync_ga4(settings: AgentSettings):
    if not settings.ga4_property_id or not settings.ga4_service_account_json:
        return {'ok': False, 'error': 'Missing GA4 property id / service account'}

    try:
        import json
        from google.oauth2 import service_account
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest,
        )
    except ImportError:
        return {'ok': False, 'error': "Install 'google-analytics-data' package"}

    try:
        creds_info = json.loads(settings.ga4_service_account_json)
        credentials = service_account.Credentials.from_service_account_info(creds_info)
        client = BetaAnalyticsDataClient(credentials=credentials)
        property_path = f"properties/{settings.ga4_property_id}"
    except Exception as exc:
        settings.is_ga4_connected = False
        settings.save(update_fields=['is_ga4_connected'])
        return {'ok': False, 'error': f'Invalid GA4 credentials: {str(exc)[:160]}'}

    # 1) Whole-site daily rollup, last 30 days
    try:
        report = client.run_report(RunReportRequest(
            property=property_path,
            dimensions=[Dimension(name='date'), Dimension(name='sessionDefaultChannelGroup')],
            metrics=[
                Metric(name='sessions'), Metric(name='totalUsers'), Metric(name='newUsers'),
                Metric(name='bounceRate'), Metric(name='averageSessionDuration'),
                Metric(name='conversions'),
            ],
            date_ranges=[DateRange(start_date='30daysAgo', end_date='today')],
        ))
    except Exception as exc:
        settings.is_ga4_connected = False
        settings.save(update_fields=['is_ga4_connected'])
        return {'ok': False, 'error': f'GA4 traffic report failed: {str(exc)[:160]}'}

    daily = {}
    for row in report.rows:
        date_str = row.dimension_values[0].value  # YYYYMMDD
        channel = row.dimension_values[1].value
        d = datetime.strptime(date_str, '%Y%m%d').date()
        bucket = daily.setdefault(d, dict(
            sessions=0, users=0, new_users=0, bounce_rate=[], duration=[],
            conversions=0, organic=0, social=0, direct=0, referral=0,
        ))
        sessions = int(float(row.metric_values[0].value))
        bucket['sessions'] += sessions
        bucket['users'] += int(float(row.metric_values[1].value))
        bucket['new_users'] += int(float(row.metric_values[2].value))
        bucket['bounce_rate'].append(float(row.metric_values[3].value))
        bucket['duration'].append(float(row.metric_values[4].value))
        bucket['conversions'] += int(float(row.metric_values[5].value))

        channel_lower = channel.lower()
        if 'organic' in channel_lower:
            bucket['organic'] += sessions
        elif 'social' in channel_lower:
            bucket['social'] += sessions
        elif 'direct' in channel_lower:
            bucket['direct'] += sessions
        else:
            bucket['referral'] += sessions

    for d, b in daily.items():
        GADailyTraffic.objects.update_or_create(
            date=d,
            defaults=dict(
                sessions=b['sessions'], users=b['users'], new_users=b['new_users'],
                bounce_rate=round(sum(b['bounce_rate']) / max(len(b['bounce_rate']), 1), 1),
                avg_session_duration_seconds=round(sum(b['duration']) / max(len(b['duration']), 1), 1),
                conversions=b['conversions'],
                source_organic=b['organic'], source_social=b['social'],
                source_direct=b['direct'], source_referral=b['referral'],
            ),
        )

    # 2) Top pages, last 30 days
    try:
        pages_report = client.run_report(RunReportRequest(
            property=property_path,
            dimensions=[Dimension(name='date'), Dimension(name='pagePath')],
            metrics=[Metric(name='screenPageViews'), Metric(name='totalUsers'),
                     Metric(name='bounceRate'), Metric(name='averageSessionDuration')],
            date_ranges=[DateRange(start_date='30daysAgo', end_date='today')],
            limit=500,
        ))
    except Exception as exc:
        settings.is_ga4_connected = False
        settings.save(update_fields=['is_ga4_connected'])
        return {'ok': False, 'error': f'GA4 pages report failed: {str(exc)[:160]}'}
    for row in pages_report.rows:
        d = datetime.strptime(row.dimension_values[0].value, '%Y%m%d').date()
        GATopPage.objects.update_or_create(
            date=d, page_path=row.dimension_values[1].value,
            defaults=dict(
                views=int(float(row.metric_values[0].value)),
                unique_visitors=int(float(row.metric_values[1].value)),
                bounce_rate=round(float(row.metric_values[2].value), 1),
                avg_duration_seconds=round(float(row.metric_values[3].value), 1),
            ),
        )

    # 3) Campaign-level sessions (UTM drill-down join key)
    try:
        campaign_report = client.run_report(RunReportRequest(
            property=property_path,
            dimensions=[Dimension(name='date'), Dimension(name='sessionCampaignName')],
            metrics=[Metric(name='sessions'), Metric(name='conversions'), Metric(name='engagedSessions')],
            date_ranges=[DateRange(start_date='30daysAgo', end_date='today')],
            limit=500,
        ))
    except Exception as exc:
        settings.is_ga4_connected = False
        settings.save(update_fields=['is_ga4_connected'])
        return {'ok': False, 'error': f'GA4 campaign report failed: {str(exc)[:160]}'}
    for row in campaign_report.rows:
        campaign = row.dimension_values[1].value
        if not campaign or campaign == '(not set)':
            continue
        d = datetime.strptime(row.dimension_values[0].value, '%Y%m%d').date()
        GACampaignSession.objects.update_or_create(
            date=d, utm_campaign=campaign,
            defaults=dict(
                sessions=int(float(row.metric_values[0].value)),
                conversions=int(float(row.metric_values[1].value)),
                engaged_sessions=int(float(row.metric_values[2].value)),
            ),
        )

    settings.is_ga4_connected = True
    settings.last_ga4_sync = timezone.now()
    settings.save(update_fields=['is_ga4_connected', 'last_ga4_sync'])
    return {'ok': True}


def sync_all():
    settings = AgentSettings.load()
    results = {}
    if settings.meta_access_token and settings.fb_page_id:
        results['facebook'] = sync_facebook(settings)
    else:
        results['facebook'] = {'ok': False, 'error': 'Missing Meta token/page id'}
    if settings.ga4_property_id and settings.ga4_service_account_json:
        results['ga4'] = sync_ga4(settings)
    else:
        results['ga4'] = {'ok': False, 'error': 'Missing GA4 property id / service account'}
    return results
