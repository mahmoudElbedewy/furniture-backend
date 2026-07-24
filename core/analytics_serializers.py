from rest_framework import serializers
from agent.models import FacebookPostMetric, GATopPage, GADailyTraffic


class FacebookPostMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = FacebookPostMetric
        fields = ('post_id', 'message', 'image_url', 'permalink_url', 'utm_campaign',
                  'reach', 'impressions', 'likes', 'comments', 'shares', 'clicks',
                  'video_views', 'post_type', 'engagement_rate', 'published_at')


class GATopPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = GATopPage
        fields = ('page_path', 'views', 'unique_visitors', 'bounce_rate', 'avg_duration_seconds')