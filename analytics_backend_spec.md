# مواصفات الباك إند للوحة التحليلات (Analytics Backend Specification)

مخصص للمساعد الذكي **Antigravity** لتطبيقه مباشرة على مشروع Django الحالي في `d:\furniture`.

---

## 1. نماذج قاعدة البيانات المقترحة (Proposed Models)

لتخزين وحساب مقاييس الويب ومزامنة منشورات ومؤشرات Meta:

### أ. تطبيق `catalog` أو تطبيق جديد `analytics`

#### `WebPageVisit`
يمثل زيارات الصفحات لتحديد الصفحات الأكثر أداءً ومصادر الترافيك:
- `path`: `CharField` (مثال: `/كنب-مودرن`)
- `session_key`: `CharField` (لتمييز الزوار الفريدين)
- `referrer_type`: `CharField` (خيارات: `direct`, `organic`, `social`, `referral`)
- `created_at`: `DateTimeField`

#### `MetaIntegration`
لتخزين إعدادات الربط مع Meta:
- `fb_page_id`: `CharField(max_length=100, blank=True)`
- `ig_user_id`: `CharField(max_length=100, blank=True)`
- `access_token`: `TextField(blank=True)`
- `is_meta_connected`: `BooleanField(default=False)`
- `is_google_connected`: `BooleanField(default=False)`
- `last_meta_sync`: `DateTimeField(null=True)`

#### `MetaPostCache`
لكاش أفضل المنشورات لتجنب الاستعلام المتكرر من Meta API:
- `post_id`: `CharField(max_length=100, unique=True)`
- `platform`: `CharField` (Facebook / Instagram)
- `caption`: `TextField`
- `image_url`: `URLField`
- `likes`: `IntegerField`
- `comments`: `IntegerField`
- `shares`: `IntegerField`
- `engagement_rate`: `FloatField`
- `posted_at`: `DateTimeField`

---

## 2. نقاط النهاية للـ API (API Endpoints)

تتطلب جميعها صلاحيات المسؤول (`IsAdminUser`).

### أ. نظرة عامة (Overview)
`GET /api/admin/analytics/overview/`
ترجع البيانات مجمعة لآخر 12 شهر:
```json
{
  "kpi": {
    "totalVisitors": 265800,
    "visitorsTrend": 12.4,
    "metaReach": 424100,
    "reachTrend": 18.2,
    "engagementRate": 4.7,
    "engagementTrend": -1.8,
    "conversionRate": 2.3,
    "conversionTrend": 0.6
  },
  "monthlyTraffic": [
    { "month": "يناير", "webVisitors": 12400, "socialReach": 34200 },
    ...
  ],
  "trafficSources": [
    { "name": "Organic", "nameAr": "بحث عضوي", "value": 9800, "color": "#6366f1" },
    ...
  ]
}
```

### ب. تحليلات الويب (Web Analytics)
`GET /api/admin/analytics/web/`
ترجع المقاييس بالتفصيل:
```json
{
  "metrics": {
    "bounceRate": 34.2,
    "bounceRateTrend": -3.1,
    "avgSessionDuration": "3:12",
    "avgSessionDurationTrend": 5.4,
    "totalSessions": 42600,
    "totalSessionsTrend": 11.8
  },
  "topPages": [
    { "name": "أطقم غرف نوم", "page": "/أطقم-غرف-نوم", "views": 12840, "uniqueVisitors": 9720, "bounceRate": 28.4, "avgDuration": "3:42" },
    ...
  ]
}
```

### ج. مركز ميتا (Meta Hub)
`GET /api/admin/analytics/meta/`
ترجع الإحصائيات من الكاش أو مباشرة من الـ API:
```json
{
  "facebook": {
    "followers": 48300,
    "followerGrowth": 5.3,
    "profileVisits": 14720,
    "postReach": 53100,
    "adSpend": 12400,
    "adClicks": 6840
  },
  "instagram": {
    "followers": 62500,
    "followerGrowth": 8.1,
    "profileVisits": 22480,
    "reelViews": 185300,
    "storyViews": 41200
  },
  "topPosts": [
    {
      "id": "fb-001",
      "platform": "facebook",
      "caption": "طقم غرفة نوم كاملة بتصميم عصري – خصم ٢٠٪ لفترة محدودة! 🛏️✨",
      "imageUrl": "https://...",
      "likes": 1240,
      "comments": 186,
      "shares": 312,
      "engagementRate": 6.8
    },
    ...
  ]
}
```

### د. الإعدادات والتحكم
`GET /api/admin/analytics/settings/`
`POST /api/admin/analytics/settings/toggle-meta/`
`POST /api/admin/analytics/settings/toggle-google/`

---

## 3. مهام المزامنة (Celery/Cron Sync Tasks)

مطلوب دالة مجدولة (Scheduled Task) تعمل كل 6 ساعات لجلب وتحديث الإحصائيات من Meta Graph API وتحديث جدول `MetaPostCache` وجدول `MetaIntegration` بالبيانات الحقيقية.
