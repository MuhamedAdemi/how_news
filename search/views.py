from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.template.response import TemplateResponse
from wagtail.models import Page

from government.models import GovItemPage
from news.models import FeedLanguage, NewsArticlePage
from videos.models import VideoPage

PAGE_SIZE = 10


def search(request):
    query = request.GET.get("query", "").strip()
    search_type = request.GET.get("type", "")
    language = request.GET.get("gjuha", "")
    page_num = request.GET.get("page", 1)

    counts = {"news": 0, "government": 0, "video": 0}
    qs = None

    if query:
        news_base = NewsArticlePage.objects.live()
        if language:
            news_base = news_base.filter(language=language)

        counts["news"] = news_base.search(query).count()
        counts["government"] = GovItemPage.objects.live().search(query).count()
        counts["video"] = VideoPage.objects.live().search(query).count()

        if search_type == "news":
            qs = news_base.search(query)
        elif search_type == "government":
            qs = GovItemPage.objects.live().search(query)
        elif search_type == "video":
            qs = VideoPage.objects.live().search(query)
        else:
            qs = (
                Page.objects.live()
                .type(NewsArticlePage, GovItemPage, VideoPage)
                .search(query)
            )

    paginator = Paginator(qs or [], PAGE_SIZE)
    try:
        results_page = paginator.page(page_num)
    except (PageNotAnInteger, EmptyPage):
        results_page = paginator.page(1)

    # Convert base Page instances to specific models so templates can access fields
    if query and not search_type:
        results_page.object_list = [p.specific for p in results_page.object_list]

    params = request.GET.copy()
    params.pop("page", None)

    return TemplateResponse(request, "search/search.html", {
        "search_query": query,
        "search_results": results_page,
        "search_type": search_type,
        "current_language": language,
        "languages": FeedLanguage.choices,
        "counts": counts,
        "total_count": sum(counts.values()),
        "filter_params": params.urlencode(),
    })
