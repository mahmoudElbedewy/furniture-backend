import logging
import requests
from datetime import timedelta
from django.db.models import Sum, Avg, Count, F
from django.utils import timezone
from rest_framework import views
from rest_framework.response import Response

from agent.models import (
    AgentSettings, FacebookPostMetric, GADailyTraffic, GATopPage,
    GACampaignSession, MetaPostCache, WebPageVisit,
)
from agent.analytics_sync import sync_all
from orders.models import Order
from chat.models import ChatConversation
from .admin_views import IsAdminRole
from .analytics_serializers import FacebookPostMetricSerializer, GATopPageSerializer

logger = logging.getLogger(__name__)


def parse_date_range(request):
    """?range=7d|30d|90d|custom&start=YYYY-MM-DD&end=YYYY-MM-DD"""
    range_key = request.query_params.get('range', '30d')
    today = timezone.localdate()
    if range_key == 'custom':
        start = request.query_params.get('start')
        end = request.query_params.get('end')
        start_date = timezone.datetime.strptime(start, '%Y-%m-%d').date() if start else today - timedelta(days=30)
        end_date = timezone.datetime.strptime(end, '%Y-%m-%d').date() if end else today
    else:
        days = {'today': 0, '7d': 7, '30d': 30, '90d': 90}.get(range_key, 30)
        start_date, end_date = today - timedelta(days=days), today
    span = (end_date - start_date).days or 1
    prev_start, prev_end = start_date - timedelta(days=span), start_date - timedelta(days=1)
    return start_date, end_date, prev_start, prev_end


def pct_change(current, previous):
    if not previous:
        return 0.0
    return round(((current - previous) / previous) * 100, 1)


def _safe_cap(val, max_val=100.0):
    """Caps a percentage at a reasonable max."""
    return min(val, max_val)


def _availability(available, source=None, reason=None):
    return {
        'available': bool(available),
        'source': source if available else None,
        'reason': None if available else reason,
    }


def _missing(key, label, reason):
    return {'key': key, 'label': label, 'reason': reason}


def _has_rows(qs):
    return qs.exists()


# ─── Helper: Meta API page access token ──────────────────────────────────
def get_page_access_token():
    """
    Returns (page_access_token, page_id, page_name, error_msg).
    All four values always returned. On error, token is None.
    """
    settings = AgentSettings.load()
    user_token = (settings.meta_access_token or '').strip()
    page_id = (settings.fb_page_id or '').strip()

    if not user_token:
        return None, page_id, '', 'no_token'

    try:
        resp = requests.get(
            'https://graph.facebook.com/v19.0/me/accounts',
            params={'access_token': user_token, 'fields': 'id,name,access_token'},
            timeout=10,
        )
        data = resp.json()

        if 'error' in data:
            err_msg = data['error'].get('message', 'Unknown Meta API error')
            return None, page_id, '', f'invalid_or_expired: {err_msg[:120]}'

        pages = data.get('data', [])
        if not pages:
            return None, page_id, '', 'no_pages_found'

        # Match by page_id if provided
        if page_id:
            for p in pages:
                if p['id'] == page_id:
                    return p['access_token'], p['id'], p.get('name', ''), None

        # Auto-detect first page
        first = pages[0]
        return first['access_token'], first['id'], first.get('name', ''), None

    except Exception as e:
        return None, page_id, '', f'connection_error: {str(e)[:100]}'


# ═══════════════════════════════════════════════════════════════════════════
# Overview Tab
# ═══════════════════════════════════════════════════════════════════════════
class AnalyticsOverviewView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        start, end, prev_start, prev_end = parse_date_range(request)
        settings = AgentSettings.load()

        # --- Website visits from WebPageVisit ---
        visits = WebPageVisit.objects.filter(created_at__date__range=(start, end)).count()
        prev_visits = WebPageVisit.objects.filter(created_at__date__range=(prev_start, prev_end)).count()

        # --- Also check GADailyTraffic if available ---
        ga_traffic = GADailyTraffic.objects.filter(date__range=(start, end))
        ga_prev = GADailyTraffic.objects.filter(date__range=(prev_start, prev_end))
        ga_sessions = ga_traffic.aggregate(v=Sum('sessions'))['v'] or 0
        ga_prev_sessions = ga_prev.aggregate(v=Sum('sessions'))['v'] or 0
        ga_conversions = ga_traffic.aggregate(v=Sum('conversions'))['v'] or 0
        ga_prev_conversions = ga_prev.aggregate(v=Sum('conversions'))['v'] or 0

        # Use whichever has data
        total_sessions = ga_sessions if ga_sessions > 0 else visits
        prev_sessions = ga_prev_sessions if ga_prev_sessions > 0 else prev_visits
        conversions = ga_conversions if ga_conversions > 0 else Order.objects.filter(
            created_at__date__range=(start, end)).count()
        prev_conversions = ga_prev_conversions if ga_prev_conversions > 0 else Order.objects.filter(
            created_at__date__range=(prev_start, prev_end)).count()

        # --- Social metrics from posts ---
        posts_qs = FacebookPostMetric.objects.filter(published_at__date__range=(start, end))
        # Also check MetaPostCache
        meta_posts_qs = MetaPostCache.objects.filter(posted_at__date__range=(start, end))

        total_reach = posts_qs.aggregate(v=Sum('reach'))['v'] or 0
        prev_reach = FacebookPostMetric.objects.filter(
            published_at__date__range=(prev_start, prev_end)
        ).aggregate(v=Sum('reach'))['v'] or 0
        total_engagement = 0
        prev_engagement = 0
        if posts_qs.exists():
            agg = posts_qs.aggregate(l=Sum('likes'), c=Sum('comments'), s=Sum('shares'))
            total_engagement = (agg['l'] or 0) + (agg['c'] or 0) + (agg['s'] or 0)
        elif meta_posts_qs.exists():
            agg = meta_posts_qs.aggregate(l=Sum('likes'), c=Sum('comments'), s=Sum('shares'))
            total_engagement = (agg['l'] or 0) + (agg['c'] or 0) + (agg['s'] or 0)
        prev_posts_qs = FacebookPostMetric.objects.filter(published_at__date__range=(prev_start, prev_end))
        if prev_posts_qs.exists():
            agg = prev_posts_qs.aggregate(l=Sum('likes'), c=Sum('comments'), s=Sum('shares'))
            prev_engagement = (agg['l'] or 0) + (agg['c'] or 0) + (agg['s'] or 0)

        # Social sessions
        social_sessions = ga_traffic.aggregate(v=Sum('source_social'))['v'] or 0
        social_visits = WebPageVisit.objects.filter(
            created_at__date__range=(start, end), referrer_type='social').count()
        content_score = 0.0
        if total_sessions > 0:
            content_score = round(((social_sessions or social_visits) / total_sessions) * 100, 1)
        content_score = _safe_cap(content_score)
        engagement_rate = round((total_engagement / total_reach) * 100, 2) if total_reach else 0.0
        prev_engagement_rate = round((prev_engagement / prev_reach) * 100, 2) if prev_reach else 0.0
        conversion_rate = round((conversions / total_sessions) * 100, 2) if total_sessions else 0.0
        prev_conversion_rate = round((prev_conversions / prev_sessions) * 100, 2) if prev_sessions else 0.0

        from django.db.models.functions import TruncMonth
        month_start = end.replace(day=1)
        first_month = (month_start - timedelta(days=365)).replace(day=1)
        ga_months = {
            row['month'].date(): row['sessions'] or 0
            for row in GADailyTraffic.objects.filter(date__gte=first_month, date__lte=end)
            .annotate(month=TruncMonth('date'))
            .values('month')
            .annotate(sessions=Sum('sessions'))
        }
        site_months = {
            row['month'].date(): row['visits'] or 0
            for row in WebPageVisit.objects.filter(created_at__date__gte=first_month, created_at__date__lte=end)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(visits=Count('id'))
        }
        reach_months = {
            row['month'].date(): row['reach'] or 0
            for row in FacebookPostMetric.objects.filter(published_at__date__gte=first_month, published_at__date__lte=end)
            .annotate(month=TruncMonth('published_at'))
            .values('month')
            .annotate(reach=Sum('reach'))
        }
        monthly_traffic = []
        cursor = first_month
        while cursor <= month_start:
            monthly_traffic.append({
                'month': cursor.strftime('%Y-%m'),
                'webVisitors': ga_months.get(cursor, site_months.get(cursor, 0)),
                'socialReach': reach_months.get(cursor, 0),
            })
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)

        if ga_sessions > 0:
            traffic_sources = [
                {'name': 'Organic', 'nameAr': 'بحث عضوي', 'value': ga_traffic.aggregate(v=Sum('source_organic'))['v'] or 0, 'color': '#16a34a'},
                {'name': 'Social', 'nameAr': 'سوشيال', 'value': ga_traffic.aggregate(v=Sum('source_social'))['v'] or 0, 'color': '#2563eb'},
                {'name': 'Direct', 'nameAr': 'مباشر', 'value': ga_traffic.aggregate(v=Sum('source_direct'))['v'] or 0, 'color': '#7c3aed'},
                {'name': 'Referral', 'nameAr': 'إحالات', 'value': ga_traffic.aggregate(v=Sum('source_referral'))['v'] or 0, 'color': '#ea580c'},
            ]
        else:
            source_rows = WebPageVisit.objects.filter(created_at__date__range=(start, end)).values('referrer_type').annotate(value=Count('id'))
            source_map = {row['referrer_type']: row['value'] for row in source_rows}
            traffic_sources = [
                {'name': 'Organic', 'nameAr': 'بحث عضوي', 'value': source_map.get('organic', 0), 'color': '#16a34a'},
                {'name': 'Social', 'nameAr': 'سوشيال', 'value': source_map.get('social', 0), 'color': '#2563eb'},
                {'name': 'Direct', 'nameAr': 'مباشر', 'value': source_map.get('direct', 0), 'color': '#7c3aed'},
                {'name': 'Referral', 'nameAr': 'إحالات', 'value': source_map.get('referral', 0), 'color': '#ea580c'},
            ]

        # Alerts
        alerts = []
        missing_data = []
        if total_sessions == 0:
            alerts.append({'severity': 'info', 'message': 'لا توجد بيانات زيارات بعد — جرب تفعيل التتبع.'})
        if not settings.meta_access_token:
            alerts.append({'severity': 'warning', 'message': 'لم يتم ربط حساب Meta بعد.'})
        if total_sessions == 0:
            missing_data.append(_missing(
                'websiteSessions',
                'Website sessions',
                'لا توجد بيانات زيارات حقيقية في هذه الفترة. فعّل تتبع الموقع أو اربط GA4.',
            ))
        if not settings.meta_access_token:
            missing_data.append(_missing(
                'meta',
                'Meta analytics',
                'لم يتم ربط Meta access token، لذلك لا يمكن جلب reach أو بيانات المنشورات من Meta.',
            ))
        if total_reach == 0 and not posts_qs.exists():
            missing_data.append(_missing(
                'totalReach',
                'Total reach',
                'لا توجد منشورات Meta متزامنة لهذه الفترة.',
            ))

        return Response({
            'kpis': {
                'totalReach': total_reach,
                'totalEngagement': total_engagement,
                'websiteSessions': total_sessions,
                'sessionsTrend': pct_change(total_sessions, prev_sessions),
                'conversions': conversions,
                'conversionsTrend': pct_change(conversions, prev_conversions),
            },
            'kpi': {
                'totalVisitors': total_sessions,
                'visitorsTrend': pct_change(total_sessions, prev_sessions),
                'metaReach': total_reach,
                'reachTrend': pct_change(total_reach, prev_reach),
                'engagementRate': engagement_rate,
                'engagementTrend': pct_change(engagement_rate, prev_engagement_rate),
                'conversionRate': conversion_rate,
                'conversionTrend': pct_change(conversion_rate, prev_conversion_rate),
            },
            'monthlyTraffic': monthly_traffic,
            'trafficSources': traffic_sources,
            'contentToTrafficScore': content_score,
            'alerts': alerts,
            'isMetaConnected': settings.is_meta_connected and bool(settings.meta_access_token),
            'isGA4Connected': settings.is_ga4_connected,
            'lastMetaSync': settings.last_meta_sync,
            'lastGA4Sync': settings.last_ga4_sync,
            'dataAvailability': {
                'websiteSessions': _availability(
                    total_sessions > 0,
                    'ga4' if ga_sessions > 0 else ('site' if visits > 0 else None),
                    'لا توجد بيانات زيارات من GA4 أو تتبع الموقع الداخلي.',
                ),
                'conversions': _availability(
                    conversions > 0,
                    'ga4' if ga_conversions > 0 else 'orders',
                    'لا توجد تحويلات في GA4 أو طلبات في هذه الفترة.',
                ),
                'meta': _availability(
                    posts_qs.exists(),
                    'facebook',
                    'لا توجد بيانات منشورات Meta متزامنة لهذه الفترة.',
                ),
            },
            'missingData': missing_data,
        })


# ═══════════════════════════════════════════════════════════════════════════
# Audience Tab
# ═══════════════════════════════════════════════════════════════════════════
class AnalyticsAudienceView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        start, end, *_ = parse_date_range(request)
        settings = AgentSettings.load()
        ga_traffic = GADailyTraffic.objects.filter(date__range=(start, end)).order_by('date')
        meta_has_synced_followers = bool(
            settings.is_meta_connected
            and settings.last_meta_sync
            and settings.fb_followers_override is not None
        )
        fb_followers = settings.fb_followers_override if meta_has_synced_followers else None
        ig_followers = (
            settings.ig_followers_override
            if settings.last_meta_sync and settings.ig_followers_override is not None
            else None
        )

        # If no GA data, use WebPageVisit
        if not ga_traffic.exists():
            visits = WebPageVisit.objects.filter(created_at__date__range=(start, end))
            by_ref = visits.values('referrer_type').annotate(cnt=Count('id'))
            source_map = {r['referrer_type']: r['cnt'] for r in by_ref}

            # Build daily user chart from visits
            from django.db.models.functions import TruncDate
            daily = visits.annotate(day=TruncDate('created_at')).values('day').annotate(cnt=Count('session_key', distinct=True)).order_by('day')

            return Response({
                'fbFollowers': fb_followers,
                'igFollowers': ig_followers,
                'sessionsBySource': [
                    {'name': 'Organic', 'value': source_map.get('organic', 0)},
                    {'name': 'Social', 'value': source_map.get('social', 0)},
                    {'name': 'Direct', 'value': source_map.get('direct', 0)},
                    {'name': 'Referral', 'value': source_map.get('referral', 0)},
                ],
                'newVsReturning': [
                    {'name': 'New', 'value': visits.values('session_key').distinct().count()},
                    {'name': 'Returning', 'value': None},
                ],
                'dailyUsers': [{'date': str(d['day']), 'users': d['cnt']} for d in daily],
                'dataAvailability': {
                    'followers': _availability(
                        meta_has_synced_followers,
                        'facebook',
                        'لا توجد مزامنة Meta ناجحة للمتابعين.',
                    ),
                    'sessionsBySource': _availability(
                        visits.exists(),
                        'site',
                        'لا توجد زيارات داخلية في هذه الفترة.',
                    ),
                    'returningUsers': _availability(
                        False,
                        None,
                        'التتبع الداخلي الحالي لا يميز المستخدم الجديد من العائد. اربط GA4 لعرضها.',
                    ),
                },
                'missingData': [
                    _missing('returningUsers', 'Returning users', 'اربط GA4 لتمييز المستخدمين العائدين.')
                ] if visits.exists() else [
                    _missing('audience', 'Audience analytics', 'لا توجد بيانات GA4 أو زيارات داخلية لهذه الفترة.')
                ],
            })

        return Response({
            'fbFollowers': fb_followers,
            'igFollowers': ig_followers,
            'sessionsBySource': [
                {'name': 'Organic', 'value': ga_traffic.aggregate(v=Sum('source_organic'))['v'] or 0},
                {'name': 'Social', 'value': ga_traffic.aggregate(v=Sum('source_social'))['v'] or 0},
                {'name': 'Direct', 'value': ga_traffic.aggregate(v=Sum('source_direct'))['v'] or 0},
                {'name': 'Referral', 'value': ga_traffic.aggregate(v=Sum('source_referral'))['v'] or 0},
            ],
            'newVsReturning': [
                {'name': 'New', 'value': ga_traffic.aggregate(v=Sum('new_users'))['v'] or 0},
                {'name': 'Returning', 'value': max(0, (ga_traffic.aggregate(v=Sum('users'))['v'] or 0)
                                                       - (ga_traffic.aggregate(v=Sum('new_users'))['v'] or 0))},
            ],
            'dailyUsers': [{'date': str(t.date), 'users': t.users} for t in ga_traffic],
            'dataAvailability': {
                'followers': _availability(
                    meta_has_synced_followers,
                    'facebook',
                    'لا توجد مزامنة Meta ناجحة للمتابعين.',
                ),
                'sessionsBySource': _availability(True, 'ga4'),
                'newVsReturning': _availability(True, 'ga4'),
            },
            'missingData': [] if meta_has_synced_followers else [
                _missing('followers', 'Social followers', 'لا توجد مزامنة Meta ناجحة للمتابعين.')
            ],
        })


# ═══════════════════════════════════════════════════════════════════════════
# Content Tab
# ═══════════════════════════════════════════════════════════════════════════
class AnalyticsContentView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        start, end, *_ = parse_date_range(request)
        posts = FacebookPostMetric.objects.filter(published_at__date__range=(start, end))[:50]
        by_type = {}
        for p in posts:
            by_type.setdefault(p.post_type, {'type': p.post_type, 'reach': 0, 'count': 0})
            by_type[p.post_type]['reach'] += p.reach
            by_type[p.post_type]['count'] += 1

        return Response({
            'posts': FacebookPostMetricSerializer(posts, many=True).data,
            'byPostType': list(by_type.values()),
            'dataAvailability': {
                'posts': _availability(
                    posts.exists(),
                    'facebook',
                    'لا توجد منشورات Meta متزامنة لهذه الفترة.',
                ),
            },
            'missingData': [] if posts.exists() else [
                _missing('posts', 'Content posts', 'شغّل مزامنة Meta بعد إضافة token وpage id صحيحين.')
            ],
        })


# ═══════════════════════════════════════════════════════════════════════════
# Web Traffic Tab (legacy)
# ═══════════════════════════════════════════════════════════════════════════
class AnalyticsWebTrafficView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        start, end, *_ = parse_date_range(request)
        traffic = GADailyTraffic.objects.filter(date__range=(start, end)).order_by('date')
        top_pages = (
            GATopPage.objects.filter(date__range=(start, end))
            .values('page_path')
            .annotate(total_views=Sum('views'), total_unique=Sum('unique_visitors'),
                      avg_bounce=Avg('bounce_rate'), avg_duration=Avg('avg_duration_seconds'))
            .order_by('-total_views')[:10]
        )

        agg = traffic.aggregate(
            sessions=Sum('sessions'), bounce=Avg('bounce_rate'), duration=Avg('avg_session_duration_seconds'),
        )
        if not traffic.exists():
            return Response({
                'metrics': {
                    'totalSessions': None,
                    'bounceRate': None,
                    'avgSessionDuration': None,
                },
                'dailyTrend': [],
                'topPages': [],
                'dataAvailability': {
                    'ga4': _availability(False, None, 'لا توجد بيانات GA4 لهذه الفترة.'),
                },
                'missingData': [
                    _missing('ga4', 'GA4 web traffic', 'اربط GA4 وشغّل المزامنة لعرض Web Traffic.')
                ],
            })
        duration_s = agg['duration'] or 0
        return Response({
            'metrics': {
                'totalSessions': agg['sessions'] or 0,
                'bounceRate': round(agg['bounce'] or 0, 1),
                'avgSessionDuration': f"{int(duration_s // 60)}:{int(duration_s % 60):02d}",
            },
            'dailyTrend': [{'date': str(t.date), 'sessions': t.sessions} for t in traffic],
            'topPages': [
                {'name': tp['page_path'], 'views': tp['total_views'], 'uniqueVisitors': tp['total_unique'],
                 'bounceRate': round(tp['avg_bounce'], 1),
                 'avgDuration': f"{int(tp['avg_duration'] // 60)}:{int(tp['avg_duration'] % 60):02d}"}
                for tp in top_pages
            ],
            'dataAvailability': {
                'ga4': _availability(True, 'ga4'),
            },
            'missingData': [],
        })


# ═══════════════════════════════════════════════════════════════════════════
# Web Analytics Tab (frontend "web" tab — uses WebPageVisit + GA fallback)
# ═══════════════════════════════════════════════════════════════════════════
class AnalyticsWebView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        from django.db.models.functions import TruncDate
        today = timezone.localdate()
        start_30 = today - timedelta(days=30)
        start_prev = today - timedelta(days=60)

        # Current period
        visits = WebPageVisit.objects.filter(created_at__date__range=(start_30, today))
        prev_visits = WebPageVisit.objects.filter(created_at__date__range=(start_prev, start_30 - timedelta(days=1)))

        total_sessions = visits.values('session_key').distinct().count() or visits.count()
        prev_sessions = prev_visits.values('session_key').distinct().count() or prev_visits.count()

        # Also try GA data
        ga = GADailyTraffic.objects.filter(date__range=(start_30, today))
        ga_prev = GADailyTraffic.objects.filter(date__range=(start_prev, start_30 - timedelta(days=1)))
        ga_sessions = ga.aggregate(v=Sum('sessions'))['v'] or 0
        ga_prev_sessions = ga_prev.aggregate(v=Sum('sessions'))['v'] or 0
        ga_bounce = ga.aggregate(v=Avg('bounce_rate'))['v'] or 0
        ga_prev_bounce = ga_prev.aggregate(v=Avg('bounce_rate'))['v'] or 0
        ga_duration = ga.aggregate(v=Avg('avg_session_duration_seconds'))['v'] or 0
        ga_prev_duration = ga_prev.aggregate(v=Avg('avg_session_duration_seconds'))['v'] or 0

        # Use GA if available, else WebPageVisit
        use_ga = ga_sessions > 0
        final_sessions = ga_sessions if use_ga else total_sessions
        final_prev_sessions = ga_prev_sessions if use_ga else prev_sessions
        bounce_rate = round(ga_bounce, 1) if use_ga else None
        prev_bounce = round(ga_prev_bounce, 1) if use_ga else None
        duration = ga_duration if use_ga else None
        prev_duration = ga_prev_duration if use_ga else None

        duration_display = None
        if duration is not None:
            dur_min = int(duration // 60)
            dur_sec = int(duration % 60)
            duration_display = f"{dur_min}:{dur_sec:02d}"

        # Top pages from WebPageVisit
        top_pages_qs = (
            visits.values('path')
            .annotate(views=Count('id'), unique_visitors=Count('session_key', distinct=True))
            .order_by('-views')[:10]
        )
        top_pages = []
        for tp in top_pages_qs:
            top_pages.append({
                'name': tp['path'].split('/')[-1] or tp['path'],
                'page': tp['path'],
                'views': tp['views'],
                'uniqueVisitors': tp['unique_visitors'],
                'bounceRate': None,
                'avgDuration': None,
            })

        # Also merge GA top pages if available
        ga_top = (
            GATopPage.objects.filter(date__range=(start_30, today))
            .values('page_path')
            .annotate(total_views=Sum('views'), total_unique=Sum('unique_visitors'),
                      avg_bounce=Avg('bounce_rate'), avg_dur=Avg('avg_duration_seconds'))
            .order_by('-total_views')[:10]
        )
        if ga_top.exists():
            top_pages = []
            for tp in ga_top:
                d = tp['avg_dur'] or 0
                top_pages.append({
                    'name': tp['page_path'].split('/')[-1] or tp['page_path'],
                    'page': tp['page_path'],
                    'views': tp['total_views'],
                    'uniqueVisitors': tp['total_unique'],
                    'bounceRate': round(tp['avg_bounce'] or 0, 1),
                    'avgDuration': f"{int(d // 60)}:{int(d % 60):02d}",
                })

        # Sparklines (last 7 data points)
        daily_sessions = (
            visits.annotate(day=TruncDate('created_at'))
            .values('day').annotate(cnt=Count('id')).order_by('day')
        )
        session_spark = [{'v': d['cnt']} for d in daily_sessions][-7:]
        if use_ga:
            session_spark = [{'v': t.sessions} for t in ga.order_by('date')][-7:]

        return Response({
            'metrics': {
                'bounceRate': bounce_rate,
                'bounceRateTrend': pct_change(bounce_rate, prev_bounce) if use_ga else None,
                'avgSessionDuration': duration_display,
                'avgSessionDurationTrend': pct_change(duration, prev_duration) if use_ga else None,
                'totalSessions': final_sessions,
                'totalSessionsTrend': pct_change(final_sessions, final_prev_sessions),
            },
            'topPages': top_pages,
            'bounceRateSparkline': [{'v': round(t.bounce_rate, 1)} for t in ga.order_by('date')][-7:] if use_ga else [],
            'sessionDurationSparkline': [{'v': t.avg_session_duration_seconds} for t in ga.order_by('date')][-7:] if use_ga else [],
            'totalSessionsSparkline': session_spark,
            'dataAvailability': {
                'totalSessions': _availability(
                    final_sessions > 0,
                    'ga4' if use_ga else ('site' if total_sessions > 0 else None),
                    'لا توجد بيانات زيارات من GA4 أو تتبع الموقع الداخلي.',
                ),
                'bounceRate': _availability(
                    use_ga,
                    'ga4',
                    'معدل الارتداد غير متاح من التتبع الداخلي. اربط GA4 لعرضه.',
                ),
                'avgSessionDuration': _availability(
                    use_ga,
                    'ga4',
                    'مدة الجلسة غير متاحة من التتبع الداخلي. اربط GA4 لعرضها.',
                ),
            },
            'missingData': [] if use_ga else [
                _missing('ga4Engagement', 'GA4 engagement metrics', 'اربط GA4 لعرض bounce rate ومدة الجلسة.')
            ],
        })


# ═══════════════════════════════════════════════════════════════════════════
# Meta Hub Tab
# ═══════════════════════════════════════════════════════════════════════════
class AnalyticsMetaView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        settings = AgentSettings.load()
        page_token, page_id, page_name, token_error = get_page_access_token()

        missing_data = []
        fb_data = {
            'followers': None,
            'followerGrowth': None,
            'profileVisits': None,
            'postReach': None,
            'adSpend': None,
            'adClicks': None,
            'weeklyFollowers': [],
            'pageName': page_name or None,
        }
        ig_data = {
            'followers': None,
            'followerGrowth': None,
            'profileVisits': None,
            'reelViews': None,
            'storyViews': None,
            'weeklyFollowers': [],
        }

        # Try getting real data from Meta Graph API
        if page_token and page_id:
            try:
                # Page info
                page_resp = requests.get(
                    f'https://graph.facebook.com/v19.0/{page_id}',
                    params={'access_token': page_token, 'fields': 'name,fan_count,talking_about_count'},
                    timeout=10,
                )
                page_info = page_resp.json()
                if 'error' not in page_info:
                    fb_data['followers'] = page_info.get('fan_count')
                    fb_data['pageName'] = page_info.get('name', fb_data['pageName'])
                    fb_data['profileVisits'] = page_info.get('talking_about_count')

                # Page insights for reach
                insights_resp = requests.get(
                    f'https://graph.facebook.com/v19.0/{page_id}/insights',
                    params={
                        'access_token': page_token,
                        'metric': 'page_impressions,page_post_engagements',
                        'period': 'days_28',
                    },
                    timeout=10,
                )
                insights = insights_resp.json()
                if 'data' in insights:
                    for metric in insights['data']:
                        if metric['name'] == 'page_impressions' and metric.get('values'):
                            fb_data['postReach'] = metric['values'][-1].get('value', 0)
            except Exception as e:
                logger.warning(f'Meta API error: {e}')
                missing_data.append(_missing('metaApi', 'Meta API', f'تعذر جلب بيانات Meta: {str(e)[:100]}'))
        else:
            missing_data.append(_missing(
                'metaConnection',
                'Meta connection',
                f'تعذر جلب بيانات Meta: {token_error}' if token_error else 'لا يوجد Meta token أو page id صالح.',
            ))

        # Top posts from MetaPostCache or FacebookPostMetric
        top_posts = []
        fb_posts = FacebookPostMetric.objects.all().order_by('-published_at')[:5]
        if fb_posts.exists():
            for p in fb_posts:
                top_posts.append({
                    'id': p.post_id,
                    'platform': 'facebook',
                    'caption': (p.message or '')[:100],
                    'imageUrl': p.image_url,
                    'likes': p.likes,
                    'comments': p.comments,
                    'shares': p.shares,
                    'engagementRate': round(p.engagement_rate, 2),
                    'date': str(p.published_at) if p.published_at else '',
                })
        else:
            meta_posts = MetaPostCache.objects.all().order_by('-posted_at')[:5]
            for p in meta_posts:
                top_posts.append({
                    'id': p.post_id,
                    'platform': p.platform,
                    'caption': (p.caption or '')[:100],
                    'imageUrl': p.image_url,
                    'likes': p.likes,
                    'comments': p.comments,
                    'shares': p.shares,
                    'engagementRate': round(p.engagement_rate, 2),
                    'date': str(p.posted_at) if p.posted_at else '',
                })

        if fb_data['followers'] is None and settings.last_meta_sync and settings.fb_followers_override is not None:
            fb_data['followers'] = settings.fb_followers_override
        if fb_data['postReach'] is None:
            local_reach = FacebookPostMetric.objects.aggregate(v=Sum('reach'))['v'] or 0
            if local_reach > 0:
                fb_data['postReach'] = local_reach

        if fb_data['followers'] is None:
            missing_data.append(_missing('facebookFollowers', 'Facebook followers', 'لم يرجع Meta API عدد المتابعين، ولا توجد قيمة متزامنة محفوظة.'))
        if fb_data['postReach'] is None:
            missing_data.append(_missing('facebookReach', 'Facebook reach', 'لا توجد insights من Meta ولا reach محفوظ من مزامنة المنشورات.'))
        missing_data.append(_missing('instagram', 'Instagram analytics', 'لا يوجد تكامل Instagram حقيقي في الباك الحالي.'))
        missing_data.append(_missing('ads', 'Meta ads', 'لا يوجد تكامل Ads Insights حقيقي في الباك الحالي.'))

        result = {
            'facebook': fb_data,
            'instagram': ig_data,
            'topPosts': top_posts,
            'dataAvailability': {
                'facebookFollowers': _availability(fb_data['followers'] is not None, 'facebook', 'لا توجد بيانات متابعين من Meta.'),
                'facebookReach': _availability(fb_data['postReach'] is not None, 'facebook', 'لا توجد بيانات reach من Meta.'),
                'topPosts': _availability(bool(top_posts), 'facebook', 'لا توجد منشورات متزامنة.'),
                'instagram': _availability(False, None, 'لا يوجد تكامل Instagram حقيقي في الباك الحالي.'),
                'ads': _availability(False, None, 'لا يوجد تكامل Ads Insights حقيقي في الباك الحالي.'),
            },
            'missingData': missing_data,
        }
        if token_error:
            result['meta_error'] = token_error

        return result if isinstance(result, Response) else Response(result)


# ═══════════════════════════════════════════════════════════════════════════
# Post Drilldown
# ═══════════════════════════════════════════════════════════════════════════
class AnalyticsPostDrilldownView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request, post_id):
        try:
            post = FacebookPostMetric.objects.get(post_id=post_id)
        except FacebookPostMetric.DoesNotExist:
            return Response({'error': 'Post not found'}, status=404)

        # A. deterministic UTM join
        campaign_sessions = GACampaignSession.objects.filter(utm_campaign=post.utm_campaign)
        sessions = campaign_sessions.aggregate(v=Sum('sessions'))['v'] or 0
        conversions = campaign_sessions.aggregate(v=Sum('conversions'))['v'] or 0
        has_utm_data = bool(post.utm_campaign and sessions > 0)

        return Response({
            'post': FacebookPostMetricSerializer(post).data,
            'attribution': {
                'method': 'utm' if has_utm_data else None,
                'sessions': sessions if has_utm_data else None,
                'conversions': conversions if has_utm_data else None,
                'note': None if has_utm_data else
                        'لا توجد بيانات UTM مطابقة لهذا المنشور في GA4، لذلك لا يمكن حساب attribution حقيقي.',
            },
            'dataAvailability': {
                'attribution': _availability(
                    has_utm_data,
                    'ga4',
                    'لا توجد جلسات GA4 مرتبطة بنفس utm_campaign.',
                ),
            },
            'missingData': [] if has_utm_data else [
                _missing('attribution', 'Post attribution', 'أضف UTM links للمنشورات وشغّل مزامنة GA4.')
            ],
        })


# ═══════════════════════════════════════════════════════════════════════════
# Settings Tab
# ═══════════════════════════════════════════════════════════════════════════
class AnalyticsSettingsView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        s = AgentSettings.load()
        _, _, page_name, token_status_msg = get_page_access_token()

        # Determine token status
        if not s.meta_access_token:
            token_status = 'no_token'
        elif token_status_msg:
            token_status = 'invalid_or_expired'
        else:
            token_status = 'valid'

        return Response({
            'fb_page_url': s.fb_page_url,
            'fb_page_id': s.fb_page_id,
            'is_meta_connected': s.is_meta_connected and bool(s.meta_access_token and s.fb_page_id),
            'last_meta_sync': s.last_meta_sync,
            'ga4_property_id': s.ga4_property_id,
            'is_ga4_connected': s.is_ga4_connected,
            'last_ga4_sync': s.last_ga4_sync,
            'admin_name': request.user.full_name or request.user.email.split('@')[0],
            'admin_email': request.user.email,
            'meta_access_token': s.meta_access_token[:20] + '...' if s.meta_access_token else '',
            'fb_followers_override': s.fb_followers_override,
            'fb_reach_override': s.fb_reach_override,
            'ig_page_url': s.ig_page_url,
            'ig_followers_override': s.ig_followers_override,
            'is_google_connected': s.is_google_connected,
            'token_status': token_status,
            'page_name': page_name or '',
        })

    def post(self, request):
        s = AgentSettings.load()
        nullable_int_fields = {'fb_followers_override', 'fb_reach_override', 'ig_followers_override'}
        for field in ('fb_page_url', 'fb_page_id', 'meta_access_token',
                      'ga4_property_id', 'ga4_service_account_json',
                      'ig_page_url'):
            if field in request.data:
                setattr(s, field, (request.data[field] or '').strip() if isinstance(request.data[field], str) else request.data[field])
        for field in nullable_int_fields:
            if field in request.data:
                value = request.data[field]
                setattr(s, field, None if value in ('', None) else int(value))
        s.is_meta_connected = bool(s.meta_access_token and s.fb_page_id)
        s.is_google_connected = bool(s.ga4_property_id and s.ga4_service_account_json)
        s.save()
        return Response({'message': 'Settings updated'})


# ═══════════════════════════════════════════════════════════════════════════
# Sync Now (manual trigger)
# ═══════════════════════════════════════════════════════════════════════════
class AnalyticsToggleMetaView(views.APIView):
    permission_classes = [IsAdminRole]

    def post(self, request):
        s = AgentSettings.load()
        enabled = bool(request.data.get('enabled', request.data.get('is_meta_connected', True)))
        if enabled and not (s.meta_access_token and s.fb_page_id):
            s.is_meta_connected = False
            s.save(update_fields=['is_meta_connected'])
            return Response({
                'ok': False,
                'is_meta_connected': False,
                'error': 'لا يمكن تفعيل Meta قبل إدخال access token و page id صحيحين.',
            }, status=400)
        s.is_meta_connected = enabled
        s.save(update_fields=['is_meta_connected'])
        return Response({'ok': True, 'is_meta_connected': s.is_meta_connected})


class AnalyticsToggleGoogleView(views.APIView):
    permission_classes = [IsAdminRole]

    def post(self, request):
        s = AgentSettings.load()
        enabled = bool(request.data.get('enabled', request.data.get('is_google_connected', True)))
        if enabled and not (s.ga4_property_id and s.ga4_service_account_json):
            s.is_google_connected = False
            s.is_ga4_connected = False
            s.save(update_fields=['is_google_connected', 'is_ga4_connected'])
            return Response({
                'ok': False,
                'is_google_connected': False,
                'is_ga4_connected': False,
                'error': 'لا يمكن تفعيل GA4 قبل إدخال property id و service account json.',
            }, status=400)
        s.is_google_connected = enabled
        s.is_ga4_connected = enabled
        s.save(update_fields=['is_google_connected', 'is_ga4_connected'])
        return Response({
            'ok': True,
            'is_google_connected': s.is_google_connected,
            'is_ga4_connected': s.is_ga4_connected,
        })


class AnalyticsSyncNowView(views.APIView):
    permission_classes = [IsAdminRole]

    def post(self, request):
        settings = AgentSettings.load()
        if settings.last_meta_sync and (timezone.now() - settings.last_meta_sync).total_seconds() < 120:
            return Response({'error': 'يرجى الانتظار دقيقتين بين عمليات المزامنة.'}, status=429)

        results = sync_all()
        ok = any(result.get('ok') for result in results.values())
        return Response({
            'message': 'Sync complete' if ok else 'Sync finished with missing configuration or provider errors',
            'ok': ok,
            'results': results,
        }, status=200 if ok else 400)
