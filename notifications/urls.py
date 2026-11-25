from django.urls import path

from . import views

urlpatterns = [
    path("notifications/", views.NotificationListView.as_view()),
    path("notifications/<int:pk>/retry/", views.NotificationRetryView.as_view()),
    path("admin/overview/", views.OverviewView.as_view()),
]
