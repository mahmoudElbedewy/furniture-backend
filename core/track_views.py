import hashlib
from rest_framework import views, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from agent.models import WebPageVisit


class TrackVisitView(views.APIView):
    """تسجيل زيارة صفحة - endpoint عام خفيف"""
    permission_classes = [AllowAny]
    throttle_classes = []  # لا حدود للتتبع

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
        
        # مفتاح الجلسة من IP + User-Agent
        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
        if ',' in ip:
            ip = ip.split(',')[0].strip()
        ua = request.META.get('HTTP_USER_AGENT', '')
        session_key = hashlib.md5(f'{ip}:{ua}'.encode()).hexdigest()[:16]
        
        WebPageVisit.objects.create(
            path=path[:500],
            session_key=session_key,
            referrer_type=referrer_type,
        )
        
        return Response({'ok': True}, status=status.HTTP_201_CREATED)
