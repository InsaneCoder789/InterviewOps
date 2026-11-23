from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("slots", views.SlotViewSet, basename="slot")
router.register("bookings", views.BookingViewSet, basename="booking")
urlpatterns = router.urls
