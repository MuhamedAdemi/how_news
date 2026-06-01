from rest_framework import serializers
from .models import GovItemPage


class GovItemListSerializer(serializers.ModelSerializer):
    item_type_display = serializers.CharField(source="get_item_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = GovItemPage
        fields = [
            "id", "title", "slug",
            "item_type", "item_type_display",
            "status", "status_display",
            "deadline", "institution", "budget",
            "original_url", "first_published_at", "url",
        ]

    def get_url(self, obj):
        try:
            return obj.get_url()
        except Exception:
            return None


class GovItemDetailSerializer(GovItemListSerializer):
    simple_explanation = serializers.CharField()
    how_to_apply = serializers.SerializerMethodField()

    class Meta(GovItemListSerializer.Meta):
        fields = GovItemListSerializer.Meta.fields + ["simple_explanation", "how_to_apply"]

    def get_how_to_apply(self, obj):
        return obj.how_to_apply.stream_data
