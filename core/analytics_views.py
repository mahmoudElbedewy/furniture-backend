import logging
import json
import requests
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db.models import Sum, Avg, Count, F, Max, Q
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
from agent.models import FunnelEvent
from agent.models import AnalyticsAlert
from catalog.models import Product, Category, SearchQuery
from orders.models import OrderItem


logger = logging.getLogger(__name__)


def parse_date_range(request):
    """?range=7d|30d|90d|custom&start=YYYY-MM-DD&end=YYYY-MM-DD&compare_to=previous_period|previous_year"""
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
    compare_to = request.query_params.get('compare_to', 'previous_period')

    if compare_to == 'previous_year':
        try:
            prev_start = start_date.replace(year=start_date.year - 1)
            prev_end = end_date.replace(year=end_date.year - 1)
        except ValueError:
            prev_start = start_date - timedelta(days=365)
            prev_end = end_date - timedelta(days=365)
    else:
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
            (row['month'].date() if hasattr(row['month'], 'date') else row['month']): row['sessions'] or 0
            for row in GADailyTraffic.objects.filter(date__gte=first_month, date__lte=end)
            .annotate(month=TruncMonth('date'))
            .values('month')
            .annotate(sessions=Sum('sessions'))
        }
        site_months = {
            (row['month'].date() if hasattr(row['month'], 'date') else row['month']): row['visits'] or 0
            for row in WebPageVisit.objects.filter(created_at__date__gte=first_month, created_at__date__lte=end)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(visits=Count('id'))
        }
        reach_months = {
            (row['month'].date() if hasattr(row['month'], 'date') else row['month']): row['reach'] or 0
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

        compare_to = request.query_params.get('compare_to', 'previous_period')
        daily_series = []
        cur_day = start
        prev_day = prev_start
        while cur_day <= end:
            v_cur = WebPageVisit.objects.filter(created_at__date=cur_day).count()
            v_prev = WebPageVisit.objects.filter(created_at__date=prev_day).count()
            ga_c = GADailyTraffic.objects.filter(date=cur_day).aggregate(s=Sum('sessions'))['s'] or 0
            ga_p = GADailyTraffic.objects.filter(date=prev_day).aggregate(s=Sum('sessions'))['s'] or 0

            reach_c = FacebookPostMetric.objects.filter(published_at__date=cur_day).aggregate(r=Sum('reach'))['r'] or 0
            reach_p = FacebookPostMetric.objects.filter(published_at__date=prev_day).aggregate(r=Sum('reach'))['r'] or 0

            ord_c = Order.objects.filter(created_at__date=cur_day).count()
            ord_p = Order.objects.filter(created_at__date=prev_day).count()

            daily_series.append({
                'date': cur_day.strftime('%m-%d'),
                'sessions': ga_c if ga_c > 0 else v_cur,
                'prevSessions': ga_p if ga_p > 0 else v_prev,
                'reach': reach_c,
                'prevReach': reach_p,
                'conversions': ord_c,
                'prevConversions': ord_p,
            })
            cur_day += timedelta(days=1)
            prev_day += timedelta(days=1)

        return Response({
            'kpis': {
                'totalReach': total_reach,
                'prevTotalReach': prev_reach,
                'totalEngagement': total_engagement,
                'prevTotalEngagement': prev_engagement,
                'websiteSessions': total_sessions,
                'prevWebsiteSessions': prev_sessions,
                'sessionsTrend': pct_change(total_sessions, prev_sessions),
                'conversions': conversions,
                'prevConversions': prev_conversions,
                'conversionsTrend': pct_change(conversions, prev_conversions),
            },
            'comparison': {
                'compareTo': compare_to,
                'prevStart': str(prev_start),
                'prevEnd': str(prev_end),
            },
            'dailyTimeSeries': daily_series,
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
# Sales & Orders Analytics
# ═══════════════════════════════════════════════════════════════════════════
class AnalyticsSalesView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        from django.db.models.functions import TruncDate

        start, end, prev_start, prev_end = parse_date_range(request)

        orders = Order.objects.filter(created_at__date__range=(start, end))
        prev_orders = Order.objects.filter(created_at__date__range=(prev_start, prev_end))

        total_revenue = orders.aggregate(v=Sum('total_price'))['v'] or 0
        prev_revenue = prev_orders.aggregate(v=Sum('total_price'))['v'] or 0
        orders_count = orders.count()
        prev_orders_count = prev_orders.count()
        aov = round(float(total_revenue) / orders_count, 2) if orders_count else 0.0
        prev_aov = round(float(prev_revenue) / prev_orders_count, 2) if prev_orders_count else 0.0

        status_labels = dict(Order.STATUS_CHOICES)
        status_rows = orders.values('status').annotate(count=Count('id')).order_by('-count')
        orders_by_status = [
            {
                'status': row['status'],
                'label': status_labels.get(row['status'], row['status']),
                'count': row['count'],
            }
            for row in status_rows
        ]

        daily_rows = (
            orders.annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(revenue=Sum('total_price'), count=Count('id'))
            .order_by('day')
        )
        daily_revenue = [
            {'date': str(row['day']), 'revenue': float(row['revenue'] or 0), 'orders': row['count']}
            for row in daily_rows
        ]

        governorate_rows = (
            orders.values('customer_governorate')
            .annotate(
                orders_count=Count('id'),
                total_revenue=Sum('total_price'),
                avg_shipping=Avg('shipping_price'),
            )
            .order_by('-orders_count')
        )
        by_governorate = [
            {
                'governorate': row['customer_governorate'] or 'غير محدد',
                'ordersCount': row['orders_count'],
                'totalRevenue': float(row['total_revenue'] or 0),
                'avgShipping': round(float(row['avg_shipping'] or 0), 2),
            }
            for row in governorate_rows
        ]

        deposit_orders_count = orders.filter(deposit_amount__gt=0).count()
        deposit_rate = round((deposit_orders_count / orders_count) * 100, 1) if orders_count else 0.0

        cancelled_orders = orders.filter(status='cancelled')
        cancelled_with_deposit_count = cancelled_orders.filter(deposit_amount__gt=0).count()
        deposit_cancelled_rate = (
            round((cancelled_with_deposit_count / orders_count) * 100, 1) if orders_count else 0.0
        )

        return Response({
            'totalRevenue': float(total_revenue),
            'revenueTrend': pct_change(float(total_revenue), float(prev_revenue)),
            'ordersCount': orders_count,
            'ordersCountTrend': pct_change(orders_count, prev_orders_count),
            'aov': aov,
            'aovTrend': pct_change(aov, prev_aov),
            'ordersByStatus': orders_by_status,
            'dailyRevenue': daily_revenue,
            'byGovernorate': by_governorate,
            'depositStats': {
                'depositOrdersRate': deposit_rate,
                'cancelledWithDepositRate': deposit_cancelled_rate,
                'note': (
                    'لا يوجد حقل مخصص لسبب الإلغاء في الموديل الحالي، فهذه النسبة '
                    'تقريبية: طلبات اتلغت وكانت أصلاً عليها ديبوزيت مطلوب.'
                ),
            },
            'dataAvailability': {
                'sales': _availability(
                    orders.exists(), 'orders', 'لا توجد طلبات في هذه الفترة.'
                ),
            },
            'missingData': [] if orders.exists() else [
                _missing('sales', 'Sales analytics', 'لا توجد طلبات مسجلة في هذه الفترة الزمنية.')
            ],
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
                {'name': 'Returning', 'value': max(0, (ga_traffic.aggregate(v=Sum('users'))['v'] or 0) - (ga_traffic.aggregate(v=Sum('new_users'))['v'] or 0))},
            ],
            'dailyUsers': [{'date': str(t.date), 'users': t.users} for t in ga_traffic],
            'dataAvailability': {
                'followers': _availability(meta_has_synced_followers, 'facebook', 'لا توجد مزامنة Meta ناجحة للمتابعين.'),
                'sessionsBySource': _availability(True, 'ga4'),
                'newVsReturning': _availability(True, 'ga4'),
            },
            'missingData': [] if meta_has_synced_followers else [_missing('followers', 'Social followers', 'لا توجد مزامنة Meta ناجحة للمتابعين.')],
        })


# ═══════════════════════════════════════════════════════════════════════════
# Content Tab
# ═══════════════════════════════════════════════════════════════════════════
class AnalyticsContentView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        start, end, prev_start, prev_end = parse_date_range(request)
        compare_to = request.query_params.get('compare_to', 'previous_period')

        posts = FacebookPostMetric.objects.filter(published_at__date__range=(start, end))[:50]
        prev_posts = FacebookPostMetric.objects.filter(published_at__date__range=(prev_start, prev_end))[:50]

        total_reach = posts.aggregate(v=Sum('reach'))['v'] or 0
        prev_reach = prev_posts.aggregate(v=Sum('reach'))['v'] or 0

        agg_cur = posts.aggregate(l=Sum('likes'), c=Sum('comments'), s=Sum('shares'))
        total_eng = (agg_cur['l'] or 0) + (agg_cur['c'] or 0) + (agg_cur['s'] or 0)

        agg_prev = prev_posts.aggregate(l=Sum('likes'), c=Sum('comments'), s=Sum('shares'))
        prev_eng = (agg_prev['l'] or 0) + (agg_prev['c'] or 0) + (agg_prev['s'] or 0)

        by_type = {}
        for p in posts:
            by_type.setdefault(p.post_type, {'type': p.post_type, 'reach': 0, 'count': 0, 'prevReach': 0})
            by_type[p.post_type]['reach'] += p.reach
            by_type[p.post_type]['count'] += 1

        for p in prev_posts:
            by_type.setdefault(p.post_type, {'type': p.post_type, 'reach': 0, 'count': 0, 'prevReach': 0})
            by_type[p.post_type]['prevReach'] += p.reach

        # Build daily series
        daily_series = []
        cur_d = start
        prv_d = prev_start
        while cur_d <= end:
            r_c = FacebookPostMetric.objects.filter(published_at__date=cur_d).aggregate(r=Sum('reach'))['r'] or 0
            r_p = FacebookPostMetric.objects.filter(published_at__date=prv_d).aggregate(r=Sum('reach'))['r'] or 0
            daily_series.append({
                'date': cur_d.strftime('%m-%d'),
                'reach': r_c,
                'prevReach': r_p,
            })
            cur_d += timedelta(days=1)
            prv_d += timedelta(days=1)

        return Response({
            'posts': FacebookPostMetricSerializer(posts, many=True).data,
            'byPostType': list(by_type.values()),
            'metrics': {
                'totalReach': total_reach,
                'prevTotalReach': prev_reach,
                'reachTrend': pct_change(total_reach, prev_reach),
                'totalEngagement': total_eng,
                'prevTotalEngagement': prev_eng,
                'engagementTrend': pct_change(total_eng, prev_eng),
            },
            'comparison': {
                'compareTo': compare_to,
                'prevStart': str(prev_start),
                'prevEnd': str(prev_end),
            },
            'dailySeries': daily_series,
            'dataAvailability': {
                'posts': _availability(posts.exists(), 'facebook', 'لا توجد منشورات Meta متزامنة لهذه الفترة.'),
            },
            'missingData': [] if posts.exists() else [_missing('posts', 'Content posts', 'شغّل مزامنة Meta بعد إضافة token وpage id صحيحين.')],
        })


# ═══════════════════════════════════════════════════════════════════════════
# Web Analytics Tab (frontend "web" tab — uses WebPageVisit + GA fallback)
# ═══════════════════════════════════════════════════════════════════════════
class AnalyticsWebView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        start, end, prev_start, prev_end = parse_date_range(request)
        compare_to = request.query_params.get('compare_to', 'previous_period')

        # Current period
        visits = WebPageVisit.objects.filter(created_at__date__range=(start, end))
        prev_visits = WebPageVisit.objects.filter(created_at__date__range=(prev_start, prev_end))

        total_sessions = visits.values('session_key').distinct().count() or visits.count()
        prev_sessions = prev_visits.values('session_key').distinct().count() or prev_visits.count()

        # Also try GA data
        ga = GADailyTraffic.objects.filter(date__range=(start, end))
        ga_prev = GADailyTraffic.objects.filter(date__range=(prev_start, prev_end))
        ga_sessions = ga.aggregate(v=Sum('sessions'))['v'] or 0
        ga_prev_sessions = ga_prev.aggregate(v=Sum('sessions'))['v'] or 0
        ga_bounce = ga.aggregate(v=Avg('bounce_rate'))['v'] or 0
        ga_prev_bounce = ga_prev.aggregate(v=Avg('bounce_rate'))['v'] or 0
        ga_duration = ga.aggregate(v=Avg('avg_session_duration_seconds'))['v'] or 0
        ga_prev_duration = ga_prev.aggregate(v=Avg('avg_session_duration_seconds'))['v'] or 0

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

        prev_duration_display = None
        if prev_duration is not None:
            dur_min = int(prev_duration // 60)
            dur_sec = int(prev_duration % 60)
            prev_duration_display = f"{dur_min}:{dur_sec:02d}"

        # Daily series for web
        daily_series = []
        cur_d = start
        prv_d = prev_start
        while cur_d <= end:
            c_v = WebPageVisit.objects.filter(created_at__date=cur_d).count()
            p_v = WebPageVisit.objects.filter(created_at__date=prv_d).count()
            c_ga = GADailyTraffic.objects.filter(date=cur_d).aggregate(s=Sum('sessions'), b=Avg('bounce_rate'))
            p_ga = GADailyTraffic.objects.filter(date=prv_d).aggregate(s=Sum('sessions'), b=Avg('bounce_rate'))

            c_s = c_ga['s'] if (c_ga['s'] and c_ga['s'] > 0) else c_v
            p_s = p_ga['s'] if (p_ga['s'] and p_ga['s'] > 0) else p_v

            daily_series.append({
                'date': cur_d.strftime('%m-%d'),
                'sessions': c_s,
                'prevSessions': p_s,
                'bounceRate': round(c_ga['b'] or 0, 1),
                'prevBounceRate': round(p_ga['b'] or 0, 1),
            })
            cur_d += timedelta(days=1)
            prv_d += timedelta(days=1)

        # Top pages
        top_pages_qs = (
            visits.values('path')
            .annotate(views=Count('id'), unique_visitors=Count('session_key', distinct=True))
            .order_by('-views')[:10]
        )
        top_pages = [
            {
                'name': tp['path'].split('/')[-1] or tp['path'],
                'page': tp['path'],
                'views': tp['views'],
                'uniqueVisitors': tp['unique_visitors'],
                'bounceRate': 0,
                'avgDuration': '0:00',
            } for tp in top_pages_qs
        ]

        # Traffic sources
        source_rows = visits.values('referrer_type').annotate(value=Count('id'))
        source_map = {row['referrer_type']: row['value'] for row in source_rows}
        traffic_sources = [
            {'name': 'Organic', 'nameAr': 'بحث عضوي', 'value': source_map.get('organic', 0), 'color': '#16a34a'},
            {'name': 'Social', 'nameAr': 'سوشيال', 'value': source_map.get('social', 0), 'color': '#2563eb'},
            {'name': 'Direct', 'nameAr': 'مباشر', 'value': source_map.get('direct', 0), 'color': '#7c3aed'},
            {'name': 'Referral', 'nameAr': 'إحالات', 'value': source_map.get('referral', 0), 'color': '#ea580c'},
        ]

        bounce_spark = [{'v': d['bounceRate']} for d in daily_series]
        session_spark = [{'v': d['sessions']} for d in daily_series]
        duration_spark = [{'v': 1} for _ in daily_series]

        return Response({
            'metrics': {
                'bounceRate': bounce_rate,
                'prevBounceRate': prev_bounce,
                'bounceRateTrend': pct_change(bounce_rate or 0, prev_bounce or 0),
                'avgSessionDuration': duration_display,
                'prevAvgSessionDuration': prev_duration_display,
                'avgSessionDurationTrend': pct_change(duration or 0, prev_duration or 0),
                'totalSessions': final_sessions,
                'prevTotalSessions': final_prev_sessions,
                'totalSessionsTrend': pct_change(final_sessions, final_prev_sessions),
            },
            'comparison': {
                'compareTo': compare_to,
                'prevStart': str(prev_start),
                'prevEnd': str(prev_end),
            },
            'dailySeries': daily_series,
            'topPages': top_pages,
            'trafficSources': traffic_sources,
            'bounceRateSparkline': bounce_spark,
            'sessionDurationSparkline': duration_spark,
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
                val = request.data[field]
                if isinstance(val, str):
                    val = val.strip()
                    if field == 'meta_access_token' and (val.endswith('...') or val.endswith('…')):
                        continue  # Do not overwrite with truncated preview token
                    setattr(s, field, val)
                else:
                    setattr(s, field, val)
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
        fb_err = results.get('facebook', {}).get('error')
        ga_err = results.get('ga4', {}).get('error')
        err_msg = fb_err or ga_err or 'فشلت المزامنة'
        if 'pages_read_engagement' in str(err_msg).lower() or 'permission' in str(err_msg).lower():
            err_msg = 'فشلت المزامنة: التوكن ينقصه صلاحية pages_read_engagement. اختر هذه الصلاحية في Graph API Explorer عند إنشاء التوكن.'
        elif 'token' in str(err_msg).lower() or 'expired' in str(err_msg).lower():
            err_msg = f'فشلت المزامنة: رمز الوصول (Access Token) غير صالح أو انتهت صلاحيته ({err_msg})'
        elif 'missing' in str(err_msg).lower():
            err_msg = 'فشلت المزامنة: يرجى إضافة Access Token و Page ID أولاً في الإعدادات.'

        return Response({
            'message': 'تمت المزامنة بنجاح ✅' if ok else 'فشلت المزامنة',
            'error': None if ok else err_msg,
            'ok': ok,
            'results': results,
        }, status=200 if ok else 400)
class AnalyticsSalesFunnelView(views.APIView):
    permission_classes = [IsAdminRole]

    STEPS = [
        ('product_view', 'مشاهدة منتج'),
        ('add_to_cart', 'إضافة للسلة'),
        ('checkout_start', 'بدء الدفع'),
        ('order_complete', 'إتمام الطلب'),
    ]

    def get(self, request):
        start, end, prev_start, prev_end = parse_date_range(request)

        events = FunnelEvent.objects.filter(created_at__date__range=(start, end))
        prev_events = FunnelEvent.objects.filter(created_at__date__range=(prev_start, prev_end))

        counts = {key: events.filter(event_type=key).count() for key, _ in self.STEPS}
        prev_counts = {key: prev_events.filter(event_type=key).count() for key, _ in self.STEPS}

        steps = []
        for idx, (key, label) in enumerate(self.STEPS):
            count = counts[key]
            prev_count = counts[self.STEPS[idx - 1][0]] if idx > 0 else count
            step_conversion = round((count / prev_count) * 100, 1) if prev_count else 0.0
            steps.append({
                'key': key,
                'label': label,
                'count': count,
                'stepConversionRate': step_conversion if idx > 0 else 100.0,
            })

        overall_conversion = round(
            (counts['order_complete'] / counts['product_view']) * 100, 2
        ) if counts['product_view'] else 0.0
        prev_overall_conversion = round(
            (prev_counts['order_complete'] / prev_counts['product_view']) * 100, 2
        ) if prev_counts['product_view'] else 0.0

        has_data = events.exists()

        return Response({
            'steps': steps,
            'overallConversionRate': overall_conversion,
            'overallConversionTrend': pct_change(overall_conversion, prev_overall_conversion),
            'dataAvailability': {
                'funnel': _availability(
                    has_data, 'site',
                    'لا توجد أحداث funnel مسجلة بعد لهذه الفترة. التتبع بدأ حديثًا فقط.',
                ),
            },
            'missingData': [] if has_data else [
                _missing('funnel', 'Conversion funnel', 'لا توجد أحداث مسجلة بعد — التتبع الجديد يحتاج وقت لتجميع بيانات.')
            ],
        })


# ═══════════════════════════════════════════════════════════════════════════
# Product Analytics Views
# ═══════════════════════════════════════════════════════════════════════════
class AnalyticsProductsTopView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        start, end, *_ = parse_date_range(request)

        products = Product.objects.select_related('category').prefetch_related('images', 'funnel_events').all()
        top_products = []
        for p in products:
            fe_views = FunnelEvent.objects.filter(product=p, event_type='product_view', created_at__date__range=(start, end)).count()
            fe_carts = FunnelEvent.objects.filter(product=p, event_type='add_to_cart', created_at__date__range=(start, end)).count()
            
            views_total = fe_views if fe_views > 0 else p.views_count
            
            order_items = OrderItem.objects.filter(product=p, order__created_at__date__range=(start, end))
            orders_cnt = order_items.aggregate(v=Sum('quantity'))['v'] or 0
            if orders_cnt == 0:
                orders_cnt = p.orders_count
                
            revenue = sum(item.price_at_order_time * item.quantity for item in order_items)
            conv_rate = round((orders_cnt / views_total) * 100, 1) if views_total > 0 else 0.0

            top_products.append({
                'id': str(p.id),
                'title': p.title,
                'slug': p.slug,
                'category_name': p.category.name if p.category else 'عام',
                'primary_image': p.primary_image_url(),
                'price': float(p.final_price),
                'views': views_total,
                'cart_adds': fe_carts,
                'orders': orders_cnt,
                'revenue': float(revenue),
                'conversion_rate': conv_rate,
            })

        top_products.sort(key=lambda x: (x['orders'], x['views']), reverse=True)

        return Response({
            'products': top_products[:10],
            'total_products': len(top_products),
        })


class AnalyticsProductsCategoriesView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        start, end, *_ = parse_date_range(request)

        categories = Category.objects.prefetch_related('products').all()
        result = []
        for cat in categories:
            cat_products = cat.products.all()
            products_count = cat_products.count()
            
            views_sum = sum(p.views_count for p in cat_products)
            
            order_items = OrderItem.objects.filter(product__category=cat, order__created_at__date__range=(start, end))
            orders_cnt = order_items.aggregate(v=Sum('quantity'))['v'] or 0
            revenue = sum(item.price_at_order_time * item.quantity for item in order_items)

            result.append({
                'id': cat.id,
                'name': cat.name,
                'slug': cat.slug,
                'products_count': products_count,
                'views': views_sum,
                'orders': orders_cnt,
                'revenue': float(revenue),
            })

        result.sort(key=lambda x: x['revenue'], reverse=True)
        return Response({'categories': result})


class AnalyticsProductsUnderperformingView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        start, end, *_ = parse_date_range(request)
        products = Product.objects.select_related('category').prefetch_related('images').all()

        underperforming = []
        for p in products:
            fe_views = FunnelEvent.objects.filter(product=p, event_type='product_view', created_at__date__range=(start, end)).count()
            views_total = fe_views if fe_views > 0 else p.views_count

            order_items = OrderItem.objects.filter(product=p, order__created_at__date__range=(start, end))
            orders_cnt = order_items.aggregate(v=Sum('quantity'))['v'] or 0

            conv_rate = round((orders_cnt / views_total) * 100, 1) if views_total > 0 else 0.0

            if views_total >= 3 and (conv_rate < 5.0 or orders_cnt == 0):
                reason = "مشاهدات عالية مقارنة بالمبيعات — يفضل مراجعة السعر أو الوصف"
                if orders_cnt == 0:
                    reason = "المنتج يعجب الزوار لكن لا يتم شاؤه — يُنصح بخصم أو توفير شحن مجاني"
                
                underperforming.append({
                    'id': str(p.id),
                    'title': p.title,
                    'slug': p.slug,
                    'category_name': p.category.name if p.category else 'عام',
                    'primary_image': p.primary_image_url(),
                    'price': float(p.final_price),
                    'views': views_total,
                    'orders': orders_cnt,
                    'conversion_rate': conv_rate,
                    'reason': reason,
                })

        underperforming.sort(key=lambda x: x['views'], reverse=True)
        return Response({'products': underperforming[:10]})


class AnalyticsFavoritesView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        from catalog.models import Product, Favorite
        from orders.models import OrderItem
        from django.db.models import Count

        # Get all products and count their favorites
        favorites_by_product = Favorite.objects.values('product').annotate(count=Count('id')).order_by('-count')

        result = []
        for item in favorites_by_product:
            p_id = item['product']
            fav_count = item['count']
            try:
                product = Product.objects.get(id=p_id)
            except Product.DoesNotExist:
                continue

            # Find all unique customer_identifiers who favorited this product
            fav_identifiers = set(Favorite.objects.filter(product=product).values_list('customer_identifier', flat=True))

            # Find all orders containing this product
            order_items = OrderItem.objects.filter(product=product).select_related('order__user')
            
            # Find which order users match our favorites
            ordered_identifiers = set()
            for oi in order_items:
                order = oi.order
                if order.user:
                    email = (order.user.email or "").strip().lower()
                    if email and "@" in email:
                        user_ident = email.split("@")[0]
                    else:
                        user_ident = str(order.user.id)
                    ordered_identifiers.add(user_ident)

            # Get session_keys from FunnelEvent for this product where event_type = 'order_complete'
            fe_sessions = set(FunnelEvent.objects.filter(product=product, event_type='order_complete').values_list('session_key', flat=True))
            ordered_identifiers.update(fe_sessions)
            
            # Count the intersection of favorited & ordered
            converted_users = fav_identifiers.intersection(ordered_identifiers)
            converted_count = len(converted_users)

            conversion_rate = round((converted_count / len(fav_identifiers)) * 100, 1) if fav_identifiers else 0.0

            result.append({
                'product_id': str(product.id),
                'product_title': product.title,
                'product_slug': product.slug,
                'product_price': float(product.final_price),
                'primary_image': product.primary_image_url(),
                'favorites_count': fav_count,
                'converted_count': converted_count,
                'conversion_rate': conversion_rate,
            })

        result.sort(key=lambda x: x['favorites_count'], reverse=True)

        return Response({
            'favorites': result[:10],
        })


# ═══════════════════════════════════════════════════════════════════════════
# Analytics Alerts
# ═══════════════════════════════════════════════════════════════════════════
class AnalyticsRealtimeView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        settings = AgentSettings.load()
        fallback_window = timezone.now() - timedelta(minutes=5)
        fallback_qs = WebPageVisit.objects.filter(created_at__gte=fallback_window)
        internal_visitors = fallback_qs.exclude(session_key='').values('session_key').distinct().count()
        if internal_visitors == 0:
            internal_visitors = fallback_qs.count()

        if settings.ga4_property_id and settings.ga4_service_account_json:
            try:
                from google.oauth2 import service_account
                from google.analytics.data_v1beta import BetaAnalyticsDataClient
                from google.analytics.data_v1beta.types import Metric, RunRealtimeReportRequest

                creds_info = json.loads(settings.ga4_service_account_json)
                credentials = service_account.Credentials.from_service_account_info(creds_info)
                client = BetaAnalyticsDataClient(credentials=credentials)
                report = client.run_realtime_report(RunRealtimeReportRequest(
                    property=f"properties/{settings.ga4_property_id}",
                    metrics=[Metric(name='activeUsers')],
                ))
                active_users = 0
                if report.rows:
                    active_users = int(float(report.rows[0].metric_values[0].value))

                return Response({
                    'currentVisitors': active_users,
                    'source': 'ga4',
                    'available': True,
                    'fallbackVisitors': internal_visitors,
                    'windowMinutes': 5,
                    'reason': None,
                })
            except Exception as exc:
                logger.warning('GA4 realtime report failed: %s', exc)

        return Response({
            'currentVisitors': internal_visitors,
            'source': 'site',
            'available': internal_visitors > 0,
            'fallbackVisitors': internal_visitors,
            'windowMinutes': 5,
            'reason': None if internal_visitors > 0 else 'GA4 Realtime API is not configured and no internal visits were recorded in the last 5 minutes.',
        })


class AnalyticsCustomersLTVView(views.APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        limit = min(int(request.query_params.get('limit', 10)), 50)
        User = get_user_model()
        customers = (
            User.objects.filter(orders__isnull=False)
            .annotate(
                lifetime_value=Sum('orders__total_price', filter=~Q(orders__status='cancelled')),
                order_count=Count('orders', filter=~Q(orders__status='cancelled'), distinct=True),
                avg_order_value=Avg('orders__total_price', filter=~Q(orders__status='cancelled')),
                last_order_at=Max('orders__created_at', filter=~Q(orders__status='cancelled')),
            )
            .filter(lifetime_value__isnull=False)
            .order_by('-lifetime_value', '-order_count')[:limit]
        )

        result = []
        for customer in customers:
            result.append({
                'id': str(customer.id),
                'email': customer.email,
                'fullName': customer.full_name,
                'phoneNumber': customer.phone_number,
                'lifetimeValue': float(customer.lifetime_value or 0),
                'orderCount': customer.order_count or 0,
                'avgOrderValue': float(customer.avg_order_value or 0),
                'lastOrderAt': customer.last_order_at.isoformat() if customer.last_order_at else None,
            })

        totals = Order.objects.filter(user__isnull=False).exclude(status='cancelled').aggregate(
            total_ltv=Sum('total_price'),
            total_orders=Count('id'),
            avg_order_value=Avg('total_price'),
        )

        return Response({
            'customers': result,
            'summary': {
                'registeredCustomers': User.objects.filter(orders__isnull=False).distinct().count(),
                'totalLifetimeValue': float(totals['total_ltv'] or 0),
                'totalOrders': totals['total_orders'] or 0,
                'avgOrderValue': float(totals['avg_order_value'] or 0),
            },
        })


class AnalyticsSearchView(views.APIView):
    permission_classes = [IsAdminRole]

    def _serialize_terms(self, qs, limit):
        rows = (
            qs.values('normalized_query')
            .annotate(
                searchCount=Count('id'),
                totalResults=Sum('results_count'),
                avgResults=Avg('results_count'),
                lastSearchedAt=Max('created_at'),
            )
            .order_by('-searchCount', 'normalized_query')[:limit]
        )
        return [
            {
                'query': row['normalized_query'],
                'searchCount': row['searchCount'] or 0,
                'totalResults': row['totalResults'] or 0,
                'avgResults': round(row['avgResults'] or 0, 1),
                'lastSearchedAt': row['lastSearchedAt'].isoformat() if row['lastSearchedAt'] else None,
            }
            for row in rows
        ]

    def get(self, request):
        start, end, *_ = parse_date_range(request)
        limit = min(int(request.query_params.get('limit', 10)), 50)
        searches = SearchQuery.objects.filter(created_at__date__range=(start, end))

        total_searches = searches.count()
        zero_result_searches = searches.filter(has_results=False).count()
        successful_searches = searches.filter(has_results=True).count()

        return Response({
            'topNoResults': self._serialize_terms(searches.filter(has_results=False), limit),
            'topSuccessful': self._serialize_terms(searches.filter(has_results=True), limit),
            'summary': {
                'totalSearches': total_searches,
                'uniqueQueries': searches.values('normalized_query').distinct().count(),
                'zeroResultSearches': zero_result_searches,
                'successfulSearches': successful_searches,
                'zeroResultRate': round((zero_result_searches / total_searches) * 100, 1) if total_searches else 0.0,
            },
        })


class AnalyticsAlertsView(views.APIView):
    """GET  /api/admin/analytics/alerts/   — جلب كل التنبيهات (مرتبة بالأحدث أولاً)"""
    permission_classes = [IsAdminRole]

    def get(self, request):
        limit = int(request.query_params.get('limit', 50))
        unread_only = request.query_params.get('unread_only', '').lower() in ('1', 'true', 'yes')

        qs = AnalyticsAlert.objects.all()
        if unread_only:
            qs = qs.filter(is_read=False)

        alerts_data = [
            {
                'id': a.id,
                'alert_type': a.alert_type,
                'severity': a.severity,
                'message': a.message,
                'detail': a.detail,
                'is_read': a.is_read,
                'created_at': a.created_at.isoformat(),
                'read_at': a.read_at.isoformat() if a.read_at else None,
                'threshold_pct': a.threshold_pct,
                'actual_value': a.actual_value,
                'previous_value': a.previous_value,
            }
            for a in qs[:limit]
        ]

        return Response({
            'alerts': alerts_data,
            'unread_count': AnalyticsAlert.objects.filter(is_read=False).count(),
            'total_count': AnalyticsAlert.objects.count(),
        })


class AnalyticsAlertReadView(views.APIView):
    """POST /api/admin/analytics/alerts/{id}/read/ — وضع علامة مقروء على تنبيه"""
    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        try:
            alert = AnalyticsAlert.objects.get(pk=pk)
        except AnalyticsAlert.DoesNotExist:
            return Response({'error': 'Alert not found'}, status=404)
        if not alert.is_read:
            alert.is_read = True
            alert.read_at = timezone.now()
            alert.save(update_fields=['is_read', 'read_at'])
        return Response({'ok': True, 'id': alert.id})


class AnalyticsAlertReadAllView(views.APIView):
    """POST /api/admin/analytics/alerts/read-all/ — وضع علامة مقروء على جميع التنبيهات"""
    permission_classes = [IsAdminRole]

    def post(self, request):
        updated = AnalyticsAlert.objects.filter(is_read=False).update(
            is_read=True,
            read_at=timezone.now(),
        )
        return Response({'ok': True, 'marked_read': updated})


class AnalyticsTriggerAlertsView(views.APIView):
    """POST /api/admin/analytics/alerts/trigger/ — تشغيل محرك التنبيهات يدوياً"""
    permission_classes = [IsAdminRole]

    def post(self, request):
        from .alert_engine import run_alert_engine
        fired = run_alert_engine()
        return Response({
            'ok': True,
            'fired': fired,
            'count': len(fired),
            'message': f'تم إنشاء {len(fired)} تنبيه جديد' if fired else 'لا توجد تنبيهات جديدة في الوقت الحالي',
        })
