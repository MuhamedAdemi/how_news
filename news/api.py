import django_filters
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import NewsArticlePage, NewsCategory
from .serializers import (
    NewsArticleListSerializer,
    NewsArticleDetailSerializer,
    NewsCategorySerializer,
)


class NewsArticleFilter(django_filters.FilterSet):
    category = django_filters.CharFilter(field_name="category__slug")
    tag = django_filters.CharFilter(method="filter_by_tag")
    source = django_filters.CharFilter(field_name="source_name", lookup_expr="icontains")

    class Meta:
        model = NewsArticlePage
        fields = ["category", "tag", "source"]

    def filter_by_tag(self, queryset, name, value):
        return queryset.filter(tags__name__iexact=value)


class NewsArticleViewSet(viewsets.ReadOnlyModelViewSet):
    filterset_class = NewsArticleFilter
    search_fields = ["title", "intro"]
    ordering_fields = ["first_published_at", "title"]
    ordering = ["-first_published_at"]
    lookup_field = "slug"

    def get_queryset(self):
        return NewsArticlePage.objects.live().order_by("-first_published_at")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return NewsArticleDetailSerializer
        return NewsArticleListSerializer

    @action(detail=False, url_path="latest")
    def latest(self, request):
        qs = self.get_queryset()[:5]
        serializer = NewsArticleListSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)


class NewsCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NewsCategory.objects.all()
    serializer_class = NewsCategorySerializer
    lookup_field = "slug"
