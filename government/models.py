from django.db import models

from wagtail.models import Page
from wagtail.fields import StreamField, RichTextField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.blocks import CharBlock, RichTextBlock, StructBlock, URLBlock
from wagtail.search import index


class GovItemType(models.TextChoices):
    TENDER = "tender", "Tender"
    GRANT = "grant", "Grant / Fond"
    COMPETITION = "competition", "Konkurs"
    LAW = "law", "Ligj / Rregullore"
    ANNOUNCEMENT = "announcement", "Njoftim"


class GovItemStatus(models.TextChoices):
    ACTIVE = "active", "Aktiv"
    UPCOMING = "upcoming", "Se shpejti"
    EXPIRED = "expired", "Ka skaduar"


class GovIndexPage(Page):
    """Faqja kryesore e seksionit qeveritar."""

    intro = RichTextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
    ]

    def get_context(self, request):
        context = super().get_context(request)
        item_type = request.GET.get("type", "")
        status = request.GET.get("status", GovItemStatus.ACTIVE)

        items = GovItemPage.objects.child_of(self).live().order_by("-first_published_at")

        if item_type:
            items = items.filter(item_type=item_type)
        if status:
            items = items.filter(status=status)

        context["items"] = items
        context["item_types"] = GovItemType.choices
        context["statuses"] = GovItemStatus.choices
        context["current_type"] = item_type
        context["current_status"] = status
        return context

    class Meta:
        verbose_name = "Government Index Page"


class GovItemPage(Page):
    """
    Elementi qeveritar individual - tender, grant, konkurs, ligj.
    Shpjegohet në gjuhë të thjeshtë për qytetarët.
    """

    item_type = models.CharField(
        max_length=20,
        choices=GovItemType.choices,
        default=GovItemType.ANNOUNCEMENT,
    )

    status = models.CharField(
        max_length=20,
        choices=GovItemStatus.choices,
        default=GovItemStatus.ACTIVE,
    )

    deadline = models.DateField(null=True, blank=True, verbose_name="Afati")

    institution = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Institucioni",
    )

    budget = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Shuma / Buxheti",
    )

    original_url = models.URLField(
        blank=True,
        verbose_name="Linku origjinal zyrtar",
    )

    # Shpjegimi i thjeshtë - kjo është vlera kryesore e platformës
    simple_explanation = RichTextField(
        verbose_name="Shpjegimi i thjeshtë për qytetarët",
        help_text="Shpjego në gjuhë të thjeshtë çfarë është, kush mund të aplikojë, dhe si.",
    )

    # Hapat e aplikimit
    how_to_apply = StreamField(
        [
            ("step", StructBlock([
                ("number", CharBlock(max_length=3)),
                ("title", CharBlock()),
                ("description", RichTextBlock()),
            ])),
            ("document_needed", CharBlock()),
            ("external_link", StructBlock([
                ("title", CharBlock()),
                ("url", URLBlock()),
            ])),
        ],
        use_json_field=True,
        blank=True,
        verbose_name="Hapat e aplikimit",
    )

    search_fields = Page.search_fields + [
        index.SearchField("simple_explanation"),
        index.FilterField("item_type"),
        index.FilterField("status"),
        index.FilterField("deadline"),
    ]

    content_panels = Page.content_panels + [
        MultiFieldPanel([
            FieldPanel("item_type"),
            FieldPanel("status"),
            FieldPanel("institution"),
            FieldPanel("deadline"),
            FieldPanel("budget"),
            FieldPanel("original_url"),
        ], heading="Detajet"),
        FieldPanel("simple_explanation"),
        FieldPanel("how_to_apply"),
    ]

    class Meta:
        verbose_name = "Government Item"
        verbose_name_plural = "Government Items"
