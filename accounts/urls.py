from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("invitations", views.InvitationViewSet)

urlpatterns = [
    path("", include(router.urls)),
    path("auth/accept-invitation/", views.AcceptInvitationView.as_view()),
    path("auth/password/", views.PasswordChangeView.as_view()),
    path("auth/password-reset/", views.PasswordResetRequestView.as_view()),
    path("auth/password-reset/confirm/", views.PasswordResetConfirmView.as_view()),
    path("auth/register/", views.RegisterView.as_view()),
    path("auth/login/", views.LoginView.as_view()),
    path("auth/logout/", views.LogoutView.as_view()),
    path("auth/me/", views.MeView.as_view()),
    path("profile/", views.MyProfileView.as_view()),
    path("mentors/", views.MentorListView.as_view()),
    path("users/<int:pk>/profile/", views.UserProfileView.as_view()),
    path("users/<int:pk>/status/", views.UserStatusView.as_view()),
    path("users/", views.UserListView.as_view()),
    path("users/<int:pk>/role/", views.UserRoleView.as_view()),
]
