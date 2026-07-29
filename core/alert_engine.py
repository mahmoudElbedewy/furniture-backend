"""
core/alert_engine.py
Alert engine — يُولِّد ويحفظ تنبيهات التحليلات مقارنةً بالفترة السابقة.
يُستدعى من Management Command أو يدوياً من View.
"""
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, Avg, Count

# ── thresholds (قابلة للتعديل) ─────────────────────────
SESSIONS_DROP_THRESHOLD_PCT = 30       # انخفاض % في الجلسات يُطلق تنبيهاً
ORDERS_DROP_THRESHOLD_PCT = 40         # انخفاض % في الطلبات
BOUNCE_RATE_SPIKE_THRESHOLD_PCT = 20   # ارتفاع % في معدل الارتداد
META_SYNC_STALE_HOURS = 24             # ساعات بدون مزامنة Meta
GA4_SYNC_STALE_HOURS = 24             # ساعات بدون مزامنة GA4
TOKEN_EXPIRY_WARN_DAYS = 3             # أيام قبل انتهاء التوكن
COOLDOWN_HOURS = 12                    # لا يتكرر نفس النوع في أقل من X ساعة


def _pct_drop(current, previous):
    """نسبة الانخفاض (موجبة = انخفض)."""
    if not previous:
        return 0.0
    return round(((previous - current) / previous) * 100, 1)


def _already_fired_recently(alert_type: str) -> bool:
    """تجنّب إصدار نفس التنبيه أكثر من مرة خلال COOLDOWN_HOURS."""
    from agent.models import AnalyticsAlert
    cutoff = timezone.now() - timedelta(hours=COOLDOWN_HOURS)
    return AnalyticsAlert.objects.filter(
        alert_type=alert_type,
        created_at__gte=cutoff,
    ).exists()


def _fire(alert_type, severity, message, detail='',
          threshold_pct=None, actual_value=None, previous_value=None):
    """أنشئ تنبيهاً واحداً وارجع True لو اتعمل."""
    from agent.models import AnalyticsAlert
    if _already_fired_recently(alert_type):
        return False
    AnalyticsAlert.objects.create(
        alert_type=alert_type,
        severity=severity,
        message=message,
        detail=detail,
        threshold_pct=threshold_pct,
        actual_value=actual_value,
        previous_value=previous_value,
    )
    return True


def run_alert_engine():
    """
    نقطة الدخول الرئيسية — شغّلها من Management Command أو يدوياً.
    تعيد قائمة بالـ alerts التي تمّ إنشاؤها.
    """
    from agent.models import AgentSettings
    from agent.models import GADailyTraffic
    from orders.models import Order

    fired = []
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    period_start = today - timedelta(days=7)
    prev_start = period_start - timedelta(days=7)
    prev_end = period_start - timedelta(days=1)

    settings = AgentSettings.load()
    now = timezone.now()

    # ── 1. Meta sync stopped ─────────────────────────────
    if settings.is_meta_connected:
        if not settings.last_meta_sync or (now - settings.last_meta_sync).total_seconds() > META_SYNC_STALE_HOURS * 3600:
            last = settings.last_meta_sync.strftime('%Y-%m-%d %H:%M') if settings.last_meta_sync else 'أبداً'
            if _fire(
                'meta_sync_stopped', 'warning',
                'توقفت مزامنة Meta منذ أكثر من 24 ساعة',
                f'آخر مزامنة ناجحة: {last}',
            ):
                fired.append('meta_sync_stopped')

    # ── 2. GA4 sync stopped ──────────────────────────────
    if settings.is_ga4_connected:
        if not settings.last_ga4_sync or (now - settings.last_ga4_sync).total_seconds() > GA4_SYNC_STALE_HOURS * 3600:
            last = settings.last_ga4_sync.strftime('%Y-%m-%d %H:%M') if settings.last_ga4_sync else 'أبداً'
            if _fire(
                'ga4_sync_stopped', 'warning',
                'توقفت مزامنة GA4 منذ أكثر من 24 ساعة',
                f'آخر مزامنة: {last}',
            ):
                fired.append('ga4_sync_stopped')

    # ── 3. Meta token expiring soon ──────────────────────
    if settings.meta_token_expires_at:
        days_left = (settings.meta_token_expires_at - now).days
        if 0 <= days_left <= TOKEN_EXPIRY_WARN_DAYS:
            if _fire(
                'meta_token_expiring', 'critical',
                f'رمز وصول Meta سينتهي خلال {days_left} يوم/أيام!',
                'يرجى تجديد الـ Access Token من صفحة الإعدادات قبل الانتهاء.',
                actual_value=float(days_left),
            ):
                fired.append('meta_token_expiring')

    # ── 4. Sessions drop ─────────────────────────────────
    curr_sessions = GADailyTraffic.objects.filter(
        date__range=(period_start, today)
    ).aggregate(v=Sum('sessions'))['v'] or 0
    prev_sessions = GADailyTraffic.objects.filter(
        date__range=(prev_start, prev_end)
    ).aggregate(v=Sum('sessions'))['v'] or 0

    if prev_sessions > 0:
        drop = _pct_drop(curr_sessions, prev_sessions)
        if drop >= SESSIONS_DROP_THRESHOLD_PCT:
            if _fire(
                'sessions_drop', 'warning',
                f'انخفضت جلسات الموقع بنسبة {drop}% مقارنةً بالأسبوع الماضي',
                f'الأسبوع الحالي: {curr_sessions} جلسة، الأسبوع السابق: {prev_sessions} جلسة',
                threshold_pct=SESSIONS_DROP_THRESHOLD_PCT,
                actual_value=float(curr_sessions),
                previous_value=float(prev_sessions),
            ):
                fired.append('sessions_drop')

    # ── 5. Bounce rate spike ──────────────────────────────
    curr_bounce = GADailyTraffic.objects.filter(
        date__range=(period_start, today)
    ).aggregate(v=Avg('bounce_rate'))['v'] or 0
    prev_bounce = GADailyTraffic.objects.filter(
        date__range=(prev_start, prev_end)
    ).aggregate(v=Avg('bounce_rate'))['v'] or 0

    if prev_bounce > 0 and curr_bounce > 0:
        bounce_change = round(((curr_bounce - prev_bounce) / prev_bounce) * 100, 1)
        if bounce_change >= BOUNCE_RATE_SPIKE_THRESHOLD_PCT:
            if _fire(
                'bounce_rate_spike', 'warning',
                f'ارتفع معدل الارتداد بنسبة {bounce_change}% هذا الأسبوع',
                f'المعدل الحالي: {round(curr_bounce, 1)}%، السابق: {round(prev_bounce, 1)}%',
                threshold_pct=BOUNCE_RATE_SPIKE_THRESHOLD_PCT,
                actual_value=round(curr_bounce, 2),
                previous_value=round(prev_bounce, 2),
            ):
                fired.append('bounce_rate_spike')

    # ── 6. Orders drop ───────────────────────────────────
    curr_orders = Order.objects.filter(
        created_at__date__range=(period_start, today)
    ).count()
    prev_orders = Order.objects.filter(
        created_at__date__range=(prev_start, prev_end)
    ).count()

    if prev_orders > 0:
        order_drop = _pct_drop(curr_orders, prev_orders)
        if order_drop >= ORDERS_DROP_THRESHOLD_PCT:
            if _fire(
                'orders_drop', 'critical',
                f'انخفضت الطلبات بنسبة {order_drop}% مقارنةً بالأسبوع الماضي',
                f'الأسبوع الحالي: {curr_orders} طلب، الأسبوع السابق: {prev_orders} طلب',
                threshold_pct=ORDERS_DROP_THRESHOLD_PCT,
                actual_value=float(curr_orders),
                previous_value=float(prev_orders),
            ):
                fired.append('orders_drop')

    return fired
