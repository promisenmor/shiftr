from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .calculations import calculate_shift
from .models import Break, Shift, WeeklyTarget


User = get_user_model()
LONDON = ZoneInfo("Europe/London")


class LondonDateTimeField(serializers.DateTimeField):
    def to_internal_value(self, value):
        raw = value if isinstance(value, datetime) else parse_datetime(str(value))
        if raw is None:
            return super().to_internal_value(value)
        if raw.second or raw.microsecond:
            raise serializers.ValidationError(
                _("Times must be entered to the nearest minute.")
            )
        if raw.utcoffset() is None:
            candidates = [
                raw.replace(tzinfo=LONDON, fold=fold)
                for fold in (0, 1)
                if raw.replace(tzinfo=LONDON, fold=fold)
                .astimezone(ZoneInfo("UTC"))
                .astimezone(LONDON)
                .replace(tzinfo=None)
                == raw
            ]
            if not candidates:
                raise serializers.ValidationError(
                    _("This local time does not exist because of a clock change.")
                )
            if len({candidate.utcoffset() for candidate in candidates}) > 1:
                raise serializers.ValidationError(
                    _("This local time is ambiguous; provide its UTC offset.")
                )
            return candidates[0]
        return super().to_internal_value(value)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "display_name")
        read_only_fields = fields


class TokenResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()


class RefreshTokenResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField(required=False)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)

    def validate_refresh(self, value):
        try:
            token = RefreshToken(value)
        except TokenError as error:
            raise serializers.ValidationError(
                _("The refresh token is invalid or expired.")
            ) from error
        if str(token.get("user_id")) != str(self.context["request"].user.pk):
            raise serializers.ValidationError(
                _("The refresh token does not belong to the authenticated user.")
            )
        self.token = token
        return value

    def save(self, **kwargs):
        self.token.blacklist()


class RegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    display_name = serializers.CharField(
        max_length=100, required=False, allow_blank=True
    )

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(_("A user with this email already exists."))
        return email

    def validate_password(self, value):
        user = User(
            email=self.initial_data.get("email", ""),
            display_name=self.initial_data.get("display_name", ""),
        )
        try:
            validate_password(value, user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages) from error
        return value

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return User.objects.create_user(**validated_data)
        except IntegrityError as error:
            raise serializers.ValidationError(
                {"email": _("A user with this email already exists.")}
            ) from error


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        email = attrs["email"].strip().lower()
        user = authenticate(
            request=self.context.get("request"),
            email=email,
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError(_("Invalid email or password."))
        attrs["user"] = user
        return attrs


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "display_name")
        read_only_fields = ("id", "email")


class BreakSerializer(serializers.ModelSerializer):
    start_at = LondonDateTimeField(required=False, allow_null=True)
    end_at = LondonDateTimeField(required=False, allow_null=True)

    class Meta:
        model = Break
        fields = ("id", "duration_minutes", "is_paid", "start_at", "end_at")
        read_only_fields = ("id",)
        extra_kwargs = {"duration_minutes": {"min_value": 0}}


class WeeklyAllocationSerializer(serializers.Serializer):
    week_start = serializers.DateField()
    minutes = serializers.IntegerField()


class ShiftSerializer(serializers.ModelSerializer):
    start_at = LondonDateTimeField(required=False, allow_null=True)
    end_at = LondonDateTimeField(required=False, allow_null=True)
    breaks = BreakSerializer(many=True, required=False)
    gross_minutes = serializers.SerializerMethodField()
    paid_break_minutes = serializers.SerializerMethodField()
    unpaid_break_minutes = serializers.SerializerMethodField()
    net_minutes = serializers.SerializerMethodField()
    weekly_allocations = serializers.SerializerMethodField()

    class Meta:
        model = Shift
        fields = (
            "id",
            "entry_mode",
            "shift_date",
            "start_at",
            "end_at",
            "duration_minutes",
            "notes",
            "breaks",
            "gross_minutes",
            "paid_break_minutes",
            "unpaid_break_minutes",
            "net_minutes",
            "weekly_allocations",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "gross_minutes",
            "paid_break_minutes",
            "unpaid_break_minutes",
            "net_minutes",
            "weekly_allocations",
            "created_at",
            "updated_at",
        )

    def create(self, validated_data):
        from .services import create_shift

        user = validated_data.pop("user")
        return create_shift(user=user, validated_data=validated_data)

    def update(self, instance, validated_data):
        from .services import update_shift

        validated_data.pop("user", None)
        return update_shift(shift=instance, validated_data=validated_data)

    def validate(self, attrs):
        instance = self.instance
        entry_mode = attrs.get(
            "entry_mode",
            instance.entry_mode if instance else None,
        )
        same_mode = (
            instance is not None
            and self.partial
            and instance.entry_mode == entry_mode
        )

        if entry_mode == Shift.EntryMode.TIMED:
            if any(
                attrs.get(field) is not None
                for field in ("shift_date", "duration_minutes")
            ):
                raise serializers.ValidationError(
                    "Timed shifts must use start_at and end_at, not duration fields."
                )
            shift_values = {
                "start_at": attrs.get("start_at", instance.start_at if same_mode else None),
                "end_at": attrs.get("end_at", instance.end_at if same_mode else None),
                "shift_date": None,
                "duration_minutes": None,
            }
        else:
            if any(attrs.get(field) is not None for field in ("start_at", "end_at")):
                raise serializers.ValidationError(
                    "Duration-only shifts cannot include start or end times."
                )
            shift_values = {
                "start_at": None,
                "end_at": None,
                "shift_date": attrs.get(
                    "shift_date", instance.shift_date if same_mode else None
                ),
                "duration_minutes": attrs.get(
                    "duration_minutes",
                    instance.duration_minutes if same_mode else None,
                ),
            }

        if "breaks" in attrs:
            breaks = attrs["breaks"]
        elif instance and self.partial:
            breaks = list(
                instance.breaks.values(
                    "duration_minutes", "is_paid", "start_at", "end_at"
                )
            )
        else:
            breaks = []

        try:
            calculate_shift(
                entry_mode=entry_mode,
                breaks=breaks,
                **shift_values,
            )
        except ValueError as error:
            raise serializers.ValidationError({"non_field_errors": [str(error)]}) from error

        attrs.update(shift_values)
        attrs["breaks"] = breaks
        return attrs

    def _calculation(self, obj):
        cache = self.context.setdefault("_shift_calculations", {})
        if obj.pk in cache:
            return cache[obj.pk]
        calculation = calculate_shift(
            entry_mode=obj.entry_mode,
            start_at=obj.start_at,
            end_at=obj.end_at,
            shift_date=obj.shift_date,
            duration_minutes=obj.duration_minutes,
            breaks=obj.breaks.all(),
        )
        cache[obj.pk] = calculation
        return calculation

    @extend_schema_field(serializers.IntegerField())
    def get_gross_minutes(self, obj):
        return self._calculation(obj).gross_minutes

    @extend_schema_field(serializers.IntegerField())
    def get_paid_break_minutes(self, obj):
        return self._calculation(obj).paid_break_minutes

    @extend_schema_field(serializers.IntegerField())
    def get_unpaid_break_minutes(self, obj):
        return self._calculation(obj).unpaid_break_minutes

    @extend_schema_field(serializers.IntegerField())
    def get_net_minutes(self, obj):
        return self._calculation(obj).net_minutes

    @extend_schema_field(WeeklyAllocationSerializer(many=True))
    def get_weekly_allocations(self, obj):
        return [
            {"week_start": week_start, "minutes": minutes}
            for week_start, minutes in sorted(
                self._calculation(obj).weekly_minutes.items()
            )
        ]


class WeeklyTargetSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeeklyTarget
        fields = ("week_start", "target_minutes", "created_at", "updated_at")
        read_only_fields = fields


class WeeklyTargetWriteSerializer(serializers.Serializer):
    target_minutes = serializers.IntegerField(min_value=0)


class WeeklySummarySerializer(serializers.Serializer):
    week_start = serializers.DateField()
    week_end = serializers.DateField()
    target_minutes = serializers.IntegerField(allow_null=True)
    suggested_target_minutes = serializers.IntegerField(allow_null=True)
    target_is_set = serializers.BooleanField()
    worked_minutes = serializers.IntegerField()
    remaining_minutes = serializers.IntegerField()
    overtime_minutes = serializers.IntegerField()
    progress_percent = serializers.IntegerField()
    shifts = ShiftSerializer(many=True)


class ShiftFilterSerializer(serializers.Serializer):
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)

    def validate(self, attrs):
        if (
            attrs.get("start_date")
            and attrs.get("end_date")
            and attrs["end_date"] < attrs["start_date"]
        ):
            raise serializers.ValidationError(
                {"end_date": _("End date must be on or after start date.")}
            )
        return attrs
