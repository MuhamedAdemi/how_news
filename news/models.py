from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import models
from django.utils.text import slugify

from wagtail.models import Page
from wagtail.fields import StreamField, RichTextField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.blocks import CharBlock, RichTextBlock, StructBlock, URLBlock
from wagtail.images.blocks import ImageChooserBlock
from wagtail.search import index
from wagtail.snippets.models import register_snippet
from modelcluster.fields import ParentalKey
from modelcluster.contrib.taggit import ClusterTaggableManager
from taggit.models import TaggedItemBase


class FeedLanguage(models.TextChoices):
    ALBANIAN = "sq", "Shqip"
    MACEDONIAN = "mk", "Maqedonisht"
    ENGLISH = "en", "Anglisht"


@register_snippet
class FeedSource(models.Model):
    """
    Burimi RSS - agjencia lajmesh.
    Wagtail @register_snippet e bën të menaxhueshëm nga paneli CMS
    pa qenë nevojë të shkruash kod ekstra.
    """
    name = models.CharField(max_length=100, verbose_name="Emri i agjencisë")
    feed_url = models.URLField(unique=True, verbose_name="URL e RSS feed")
    language = models.CharField(
        max_length=2,
        choices=FeedLanguage.choices,
        default=FeedLanguage.ALBANIAN,
    )
    is_active = models.BooleanField(default=True, verbose_name="Aktiv")
    last_fetched = models.DateTimeField(null=True, blank=True)

    panels = [
        FieldPanel("name"),
        FieldPanel("feed_url"),
        FieldPanel("language"),
        FieldPanel("is_active"),
    ]

    def __str__(self):
        return f"{self.name} ({self.get_language_display()})"

    class Meta:
        verbose_name = "Feed Source"
        verbose_name_plural = "Feed Sources"


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
        articles = (
            NewsArticlePage.objects.child_of(self)
            .live()
            .order_by("-first_published_at")
        )
        paginator = Paginator(articles, 12)
        page_num = request.GET.get("faqe", 1)
        try:
            context["articles"] = paginator.page(page_num)
        except (PageNotAnInteger, EmptyPage):
            context["articles"] = paginator.page(1)
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

    # URL origjinale e lajmit — përdoret për të shmangur duplikatet
    source_url = models.URLField(max_length=500, blank=True, db_index=True)
    source_name = models.CharField(max_length=100, blank=True)

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
