from django.db import models
from django.utils.text import slugify

from wagtail.models import Page
from wagtail.fields import StreamField, RichTextField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.blocks import CharBlock, RichTextBlock, StructBlock, URLBlock
from wagtail.images.blocks import ImageChooserBlock
from wagtail.search import index
from modelcluster.fields import ParentalKey
from modelcluster.contrib.taggit import ClusterTaggableManager
from taggit.models import TaggedItemBase


class NewsTag(TaggedItemBase):
    content_object = ParentalKey(
        "NewsArticlePage",
        related_name="tagged_items",
        on_delete=models.CASCADE,
    )


class NewsCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "News Categories"


class NewsIndexPage(Page):
    """Faqja kryesore e seksionit të lajmeve - liston të gjitha artikujt."""

    intro = RichTextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
    ]

    def get_context(self, request):
        context = super().get_context(request)
        context["articles"] = (
            NewsArticlePage.objects.child_of(self)
            .live()
            .order_by("-first_published_at")
        )
        return context

    class Meta:
        verbose_name = "News Index Page"


class NewsArticlePage(Page):
    """Artikulli individual i lajmit."""

    cover_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    intro = models.TextField(max_length=500, blank=True)

    # StreamField - redaktori shton paragrafë, foto, citate lirisht
    body = StreamField(
        [
            ("paragraph", RichTextBlock()),
            ("image", ImageChooserBlock()),
            ("quote", StructBlock([
                ("text", CharBlock()),
                ("author", CharBlock(required=False)),
            ])),
            ("external_link", StructBlock([
                ("title", CharBlock()),
                ("url", URLBlock()),
            ])),
        ],
        use_json_field=True,
        blank=True,
    )

    tags = ClusterTaggableManager(through=NewsTag, blank=True)

    category = models.ForeignKey(
        NewsCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="articles",
    )

    search_fields = Page.search_fields + [
        index.SearchField("intro"),
        index.SearchField("body"),
    ]

    content_panels = Page.content_panels + [
        MultiFieldPanel([
            FieldPanel("cover_image"),
            FieldPanel("intro"),
            FieldPanel("category"),
            FieldPanel("tags"),
        ], heading="Article Info"),
        FieldPanel("body"),
    ]

    class Meta:
        verbose_name = "News Article"
