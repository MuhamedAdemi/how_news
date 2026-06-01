from rest_framework import serializers
from .models import NewsArticlePage, NewsCategory, FeedSource


class NewsCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsCategory
        fields = ["id", "name", "slug"]


class FeedSourceSerializer(serializers.ModelSerializer):
    language_display = serializers.CharField(source="get_language_display", read_only=True)

    class Meta:
        model = FeedSource
        fields = ["id", "name", "language", "language_display", "last_fetched"]


class NewsArticleListSerializer(serializers.ModelSerializer):
    category = NewsCategorySerializer(read_only=True)
    tags = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta:
        model = NewsArticlePage
        fields = [
            "id", "title", "slug", "intro",
            "source_url", "source_name",
            "cover_image_url", "category", "tags",
            "first_published_at", "url",
        ]

    def get_tags(self, obj):
        return list(obj.tags.names())

    def get_cover_image_url(self, obj):
        if not obj.cover_image_id:
            return None
        try:
            return obj.cover_image.get_rendition("fill-800x450").url
        except Exception:
            return None

    def get_url(self, obj):
        try:
            return obj.get_url()
        except Exception:
            return None


class NewsArticleDetailSerializer(NewsArticleListSerializer):
    body = serializers.SerializerMethodField()

    class Meta(NewsArticleListSerializer.Meta):
        fields = NewsArticleListSerializer.Meta.fields + ["body"]

    def get_body(self, obj):
        return obj.body.stream_data
