from django.utils.html import format_html
from wagtail import hooks
from wagtail.admin.ui.components import Component


class HowNewsSummaryPanel(Component):
    """Panel ne dashboardin e admin me statistika te platformes."""

    order = 50

    def render_html(self, parent_context=None):
        from news.models import FeedSource, NewsArticlePage
        from government.models import GovItemPage, GovItemStatus
        from videos.models import VideoPage

        news_count = NewsArticlePage.objects.live().count()
        gov_count = GovItemPage.objects.live().filter(status=GovItemStatus.ACTIVE).count()
        video_count = VideoPage.objects.live().count()
        feeds_count = FeedSource.objects.filter(is_active=True).count()

        last = (
            FeedSource.objects.filter(last_fetched__isnull=False)
            .order_by("-last_fetched")
            .first()
        )
        last_fetch = (
            last.last_fetched.strftime("%d %b %Y, %H:%M") if last else "Asnje here"
        )

        return format_html(
            """
<section class="w-panel">
  <div class="w-panel__header">
    <h2 class="w-panel__heading w-panel__heading--label">
      HoW News &mdash; Gjendja e platformes
    </h2>
  </div>
  <div class="w-panel__content" style="padding:1.25rem 1.5rem;">
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:1.5rem;text-align:center;margin-bottom:1rem;">
      <div>
        <div style="font-size:2.2rem;font-weight:700;color:#1d4ed8;line-height:1">{}</div>
        <div style="font-size:.8rem;color:#6b7280;margin-top:.25rem;">Artikuj Lajmesh</div>
      </div>
      <div>
        <div style="font-size:2.2rem;font-weight:700;color:#16a34a;line-height:1">{}</div>
        <div style="font-size:.8rem;color:#6b7280;margin-top:.25rem;">Qeveria Aktive</div>
      </div>
      <div>
        <div style="font-size:2.2rem;font-weight:700;color:#dc2626;line-height:1">{}</div>
        <div style="font-size:.8rem;color:#6b7280;margin-top:.25rem;">Video</div>
      </div>
      <div>
        <div style="font-size:2.2rem;font-weight:700;color:#f59e0b;line-height:1">{}</div>
        <div style="font-size:.8rem;color:#6b7280;margin-top:.25rem;">RSS Aktive</div>
      </div>
    </div>
    <p style="margin:0;font-size:.8rem;color:#9ca3af;text-align:center;padding-top:1rem;border-top:1px solid #f3f4f6;">
      Fetch i fundit: <strong>{}</strong>
    </p>
  </div>
</section>
""",
            news_count,
            gov_count,
            video_count,
            feeds_count,
            last_fetch,
        )


@hooks.register("construct_homepage_panels")
def add_how_news_panel(request, panels):
    panels.insert(0, HowNewsSummaryPanel())


@hooks.register("insert_global_admin_css")
def global_admin_css():
    return format_html(
        """<style>
:root {{
    --w-color-primary: #1d4ed8;
    --w-color-primary-200: #bfdbfe;
}}
.w-slim-header {{
    background: linear-gradient(90deg, #1e3a8a 0%, #1d4ed8 100%) !important;
}}
</style>"""
    )
