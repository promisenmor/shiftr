from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

from .views import (
    LoginView,
    LogoutView,
    GoogleSSOView,
    ProfileView,
    RegisterView,
    RefreshView,
    ShiftDetailView,
    ShiftListCreateView,
    WeeklySummaryView,
    WeeklyTargetDetailView,
    WeeklyTargetListView,
)


urlpatterns = [
    path(
        "schema/",
        SpectacularAPIView.as_view(
            permission_classes=[AllowAny],
            authentication_classes=[],
        ),
        name="schema",
    ),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema",
            permission_classes=[AllowAny],
            authentication_classes=[],
        ),
        name="swagger-ui",
    ),
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/google/", GoogleSSOView.as_view(), name="google-sso"),
    path("auth/refresh/", RefreshView.as_view(), name="token-refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("shifts/", ShiftListCreateView.as_view(), name="shift-list"),
    path("shifts/<int:pk>/", ShiftDetailView.as_view(), name="shift-detail"),
    path("weekly-targets/", WeeklyTargetListView.as_view(), name="weekly-target-list"),
    path(
        "weekly-targets/<str:week_start>/",
        WeeklyTargetDetailView.as_view(),
        name="weekly-target-detail",
    ),
    path(
        "weeks/<str:week_start>/summary/",
        WeeklySummaryView.as_view(),
        name="weekly-summary",
    ),
]
