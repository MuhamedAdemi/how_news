from rest_framework.routers import DefaultRouter

from news.api import NewsArticleViewSet, NewsCategoryViewSet
from government.api import GovItemViewSet
from videos.api import VideoPageViewSet

router = DefaultRouter()
router.register("news", NewsArticleViewSet, basename="news")
router.register("news-categories", NewsCategoryViewSet, basename="news-category")
router.register("government", GovItemViewSet, basename="government")
router.register("videos", VideoPageViewSet, basename="video")

urlpatterns = router.urls
