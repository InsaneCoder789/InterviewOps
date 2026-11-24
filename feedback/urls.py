from django.urls import path

from . import views

urlpatterns = [
    path("feedback/", views.FeedbackListView.as_view()),
    path("feedback/progress/", views.ProgressView.as_view()),
    path("bookings/<int:pk>/feedback/", views.BookingFeedbackView.as_view()),
]
