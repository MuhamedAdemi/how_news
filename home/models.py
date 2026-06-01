from django.db import models
from wagtail.models import Page
from news.models import NewsArticlePage
from government.models import GovItemPage, GovItemStatus
from videos.models import VideoPage


class HomePage(Page):

    def get_context(self, request):
        context = super().get_context(request)
        context["latest_news"] = (
            NewsArticlePage.objects.live().order_by("-first_published_at")[:6]
        )
        context["active_gov_items"] = (
            GovItemPage.objects.live()
            .filter(status=GovItemStatus.ACTIVE)
            .order_by("-first_published_at")[:4]
        )
        context["latest_videos"] = (
            VideoPage.objects.live().order_by("-first_published_at")[:3]
        )
        return context
