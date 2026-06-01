import django_filters
from rest_framework import viewsets

from .models import GovItemPage, GovItemType, GovItemStatus
from .serializers import GovItemListSerializer, GovItemDetailSerializer


class GovItemFilter(django_filters.FilterSet):
    type = django_filters.ChoiceFilter(field_name="item_type", choices=GovItemType.choices)
    status = django_filters.ChoiceFilter(field_name="status", choices=GovItemStatus.choices)
    institution = django_filters.CharFilter(field_name="institution", lookup_expr="icontains")
    deadline_before = django_filters.DateFilter(field_name="deadline", lookup_expr="lte")
    deadline_after = django_filters.DateFilter(field_name="deadline", lookup_expr="gte")

    class Meta:
        model = GovItemPage
        fields = ["type", "status", "institution", "deadline_before", "deadline_after"]


class GovItemViewSet(viewsets.ReadOnlyModelViewSet):
    filterset_class = GovItemFilter
    search_fields = ["title", "institution", "simple_explanation"]
    ordering_fields = ["first_published_at", "deadline", "title"]
    ordering = ["-first_published_at"]
    lookup_field = "slug"

    def get_queryset(self):
        return GovItemPage.objects.live().order_by("-first_published_at")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return GovItemDetailSerializer
        return GovItemListSerializer
