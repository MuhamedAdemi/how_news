from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import models

from wagtail.models import Page
from wagtail.fields import RichTextField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.embeds.blocks import EmbedBlock
from wagtail.fields import StreamField
from wagtail.search import index


class VideoCategory(models.TextChoices):
    EDUCATION = "education", "Edukim"
    RIGHTS = "rights", "Të Drejta"
    HEALTH = "health", "Shëndetësi"
    ECONOMY = "economy", "Ekonomi"
    ENVIRONMENT = "environment", "Mjedis"
    OTHER = "other", "Tjetër"


class VideoIndexPage(Page):
    """Faqja kryesore e videos - liston të gjitha videot."""

    intro = RichTextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
    ]

    def get_context(self, request):
        context = super().get_context(request)
        category = request.GET.get("category", "")
        videos = VideoPage.objects.child_of(self).live().order_by("-first_published_at")
        if category:
            videos = videos.filter(category=category)
        paginator = Paginator(videos, 9)
        page_num = request.GET.get("faqe", 1)
        try:
            context["videos"] = paginator.page(page_num)
        except (PageNotAnInteger, EmptyPage):
            context["videos"] = paginator.page(1)
        context["categories"] = VideoCategory.choices
        context["current_category"] = category
        return context

    class Meta:
        verbose_name = "Video Index Page"


class VideoPage(Page):
    """
    Video individuale e HoW staff.
    Embed nga YouTube/Vimeo - nuk nevojitet të ngarkosh videon.
    """

    # URL e videos YouTube ose Vimeo - Wagtail e embeds automatikisht
    video_url = models.URLField(
        verbose_name="URL e videos (YouTube / Vimeo)",
    )

    category = models.CharField(
        max_length=20,
        choices=VideoCategory.choices,
        default=VideoCategory.OTHER,
    )

    cover_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Foto thumbnail (opsionale)",
    )

    description = RichTextField(
        blank=True,
        verbose_name="Pershkrimi i videos",
    )

    presenter = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Prezantuesi / Eksperti",
    )

    duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Kohëzgjatja (minuta)",
    )

    search_fields = Page.search_fields + [
        index.SearchField("description"),
        index.SearchField("presenter"),
        index.FilterField("category"),
    ]

    content_panels = Page.content_panels + [
        MultiFieldPanel([
            FieldPanel("video_url"),
            FieldPanel("category"),
            FieldPanel("cover_image"),
            FieldPanel("presenter"),
            FieldPanel("duration_minutes"),
        ], heading="Video Info"),
        FieldPanel("description"),
    ]

    class Meta:
        verbose_name = "Video"
        verbose_name_plural = "Videos"
