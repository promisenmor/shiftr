from datetime import date

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    PermissionDenied,
    ValidationError,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .google_sso import GoogleAccountConflict, get_or_create_google_user
from .models import Shift
from .selectors import (
    shifts_for_user,
    weekly_summary_for_user,
    weekly_targets_for_user,
)
from .serializers import (
    GoogleSSOSerializer,
    LoginSerializer,
    LogoutSerializer,
    ProfileSerializer,
    RefreshTokenResponseSerializer,
    RegistrationSerializer,
    ShiftFilterSerializer,
    ShiftSerializer,
    TokenResponseSerializer,
    UserSerializer,
    WeeklySummarySerializer,
    WeeklyTargetSerializer,
    WeeklyTargetWriteSerializer,
)
from .services import delete_shift, set_weekly_target


class GoogleCredentialError(Exception):
    pass


class GoogleSSOUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = _("Google sign-in is not configured.")


def verify_oauth2_token(credential, *, audience):
    from google.auth.exceptions import GoogleAuthError
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2.id_token import verify_oauth2_token as google_verify_token

    try:
        return google_verify_token(
            credential,
            GoogleAuthRequest(timeout=5),
            audience=audience,
        )
    except (GoogleAuthError, ValueError) as error:
        raise GoogleCredentialError from error


def _parse_week_start(value):
    try:
        week_start = date.fromisoformat(value)
    except ValueError as error:
        raise ValidationError(
            {"week_start": _("Use an ISO date in YYYY-MM-DD format.")}
        ) from error
    if week_start.isoformat() != value:
        raise ValidationError(
            {"week_start": _("Use an ISO date in YYYY-MM-DD format.")}
        )
    if week_start.weekday() != 0:
        raise ValidationError({"week_start": _("The week must start on a Monday.")})
    return week_start


class RegisterView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        request=RegistrationSerializer,
        responses={201: TokenResponseSerializer, 400: None},
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        request=LoginSerializer,
        responses={200: TokenResponseSerializer, 400: None},
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            }
        )


class GoogleSSOView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        request=GoogleSSOSerializer,
        responses={200: TokenResponseSerializer, 400: None, 401: None, 503: None},
        tags=["Authentication"],
        description=(
            "Verify a Google Identity Services ID-token credential, then register "
            "or sign in the matching account and return Shiftr JWTs. Existing "
            "accounts are linked only when Google's verified email matches."
        ),
    )
    def post(self, request):
        client_id = getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "")
        if not client_id:
            raise GoogleSSOUnavailable()

        serializer = GoogleSSOSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            claims = verify_oauth2_token(
                serializer.validated_data["credential"],
                audience=client_id,
            )
        except (GoogleCredentialError, ValueError) as error:
            raise AuthenticationFailed(
                _("The Google credential is invalid or expired.")
            ) from error

        subject = claims.get("sub")
        email = claims.get("email")
        if (
            not isinstance(subject, str)
            or not subject
            or not isinstance(email, str)
            or not email
            or claims.get("email_verified") is not True
        ):
            raise AuthenticationFailed(
                _("Google must provide a verified email address.")
            )

        display_name = claims.get("name", "")
        if not isinstance(display_name, str):
            display_name = ""
        try:
            user = get_or_create_google_user(
                subject=subject,
                email=email,
                display_name=display_name,
            )
        except GoogleAccountConflict as error:
            raise PermissionDenied(str(error)) from error

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            }
        )


class RefreshView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        request=TokenRefreshSerializer,
        responses={200: RefreshTokenResponseSerializer, 401: None},
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = TokenRefreshSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as error:
            raise InvalidToken(_("The refresh token is invalid or expired.")) from error
        return Response(serializer.validated_data)


class LogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        request=LogoutSerializer,
        responses={204: None},
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = LogoutSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    get=extend_schema(responses=ProfileSerializer, tags=["Profile"]),
    patch=extend_schema(
        request=ProfileSerializer,
        responses=ProfileSerializer,
        tags=["Profile"],
    ),
)
class ProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ProfileSerializer

    def get_object(self):
        return self.request.user


@extend_schema_view(
    get=extend_schema(
        parameters=[ShiftFilterSerializer],
        responses=ShiftSerializer(many=True),
        tags=["Shifts"],
    ),
    post=extend_schema(
        request=ShiftSerializer,
        responses={201: ShiftSerializer},
        tags=["Shifts"],
    ),
)
class ShiftListCreateView(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ShiftSerializer

    def get_queryset(self):
        filters = ShiftFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        return shifts_for_user(self.request.user, **filters.validated_data)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


@extend_schema_view(
    get=extend_schema(responses=ShiftSerializer, tags=["Shifts"]),
    patch=extend_schema(
        request=ShiftSerializer,
        responses=ShiftSerializer,
        tags=["Shifts"],
    ),
    put=extend_schema(
        request=ShiftSerializer,
        responses=ShiftSerializer,
        tags=["Shifts"],
    ),
    delete=extend_schema(request=None, responses={204: None}, tags=["Shifts"]),
)
class ShiftDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ShiftSerializer
    queryset = Shift.objects.prefetch_related("breaks")

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_destroy(self, instance):
        delete_shift(shift=instance)


class WeeklyTargetListView(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = WeeklyTargetSerializer

    @extend_schema(responses=WeeklyTargetSerializer(many=True), tags=["Weekly targets"])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return weekly_targets_for_user(self.request.user)


class WeeklyTargetDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        request=WeeklyTargetWriteSerializer,
        responses=WeeklyTargetSerializer,
        tags=["Weekly targets"],
    )
    def put(self, request, week_start):
        monday = _parse_week_start(week_start)

        serializer = WeeklyTargetWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = set_weekly_target(
            user=request.user,
            week_start=monday,
            target_minutes=serializer.validated_data["target_minutes"],
        )
        return Response(WeeklyTargetSerializer(target).data)


class WeeklySummaryView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        responses=WeeklySummarySerializer,
        tags=["Weekly summary"],
    )
    def get(self, request, week_start):
        monday = _parse_week_start(week_start)
        summary = weekly_summary_for_user(request.user, monday)
        return Response(WeeklySummarySerializer(summary).data)
