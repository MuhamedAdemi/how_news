from rest_framework import serializers
from .models import VideoPage


class VideoListSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    cover_image_url = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta:
        model = VideoPage
        fields = [
            "id", "title", "slug",
            "video_url", "category", "category_display",
            "cover_image_url", "presenter", "duration_minutes",
            "first_published_at", "url",
        ]

    def get_cover_image_url(self, obj):
        if not obj.cover_image_id:
            return None
        try:
            return obj.cover_image.get_rendition("fill-640x360").url
        except Exception:
            return None

    def get_url(self, obj):
        try:
            return obj.get_url()
        except Exception:
            return None


class VideoDetailSerializer(VideoListSerializer):
    description = serializers.CharField()

    class Meta(VideoListSerializer.Meta):
        fields = VideoListSerializer.Meta.fields + ["description"]
