from rest_framework import views, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from agent.models import WebPageVisit
from agent.models import FunnelEvent
from catalog.models import Product
from core.tracking import record_funnel_event, visitor_session_key


class TrackVisitView(views.APIView):
    """تسجيل زيارة صفحة - endpoint عام خفيف"""
    permission_classes = [AllowAny]
    throttle_classes = []  

    def post(self, request):
        path = request.data.get('path', '/')
        referrer = request.data.get('referrer', '')
        
        # تحديد نوع المصدر
        referrer_type = 'direct'
        if referrer:
            r_lower = referrer.lower()
            if any(s in r_lower for s in ['google', 'bing', 'yahoo', 'duckduckgo']):
                referrer_type = 'organic'
            elif any(s in r_lower for s in ['facebook', 'instagram', 'twitter', 'tiktok', 'fb.com', 't.co']):
                referrer_type = 'social'
            else:
                referrer_type = 'referral'
        
        session_key = visitor_session_key(request)
        
        WebPageVisit.objects.create(
            path=path[:500],
            session_key=session_key,
            referrer_type=referrer_type,
        )
        
        return Response({'ok': True}, status=status.HTTP_201_CREATED)
class TrackFunnelEventView(views.APIView):
    """تسجيل حدث funnel (مشاهدة/سلة/دفع/طلب) - endpoint عام خفيف"""
    permission_classes = [AllowAny]
    throttle_classes = []

    # Completed orders are only recorded by OrderCreateView. Keeping this
    # event off the public endpoint prevents browser retries or forged calls
    # from corrupting revenue-conversion reporting.
    VALID_EVENTS = {c[0] for c in FunnelEvent.EVENT_CHOICES} - {"order_complete"}

    def post(self, request):
        event_type = request.data.get('event_type')
        if event_type not in self.VALID_EVENTS:
            return Response({'error': 'invalid event_type'}, status=status.HTTP_400_BAD_REQUEST)

        product_id = request.data.get('product_id')
        product = None
        if product_id:
            product = Product.objects.filter(id=product_id).first()

        record_funnel_event(request, event_type, product=product)
        return Response({'ok': True}, status=status.HTTP_201_CREATED)
