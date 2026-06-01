import django_filters
from rest_framework import viewsets

from .models import VideoPage, VideoCategory
from .serializers import VideoListSerializer, VideoDetailSerializer


class VideoFilter(django_filters.FilterSet):
    category = django_filters.ChoiceFilter(choices=VideoCategory.choices)
    presenter = django_filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = VideoPage
        fields = ["category", "presenter"]


class VideoPageViewSet(viewsets.ReadOnlyModelViewSet):
    filterset_class = VideoFilter
    search_fields = ["title", "description", "presenter"]
    ordering_fields = ["first_published_at", "title", "duration_minutes"]
    ordering = ["-first_published_at"]
    lookup_field = "slug"

    def get_queryset(self):
        return VideoPage.objects.live().order_by("-first_published_at")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return VideoDetailSerializer
        return VideoListSerializer
