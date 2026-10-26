from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _


class UserManager(DjangoUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("A superuser must have staff and superuser permissions.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField(_("email address"), unique=True)
    display_name = models.CharField(max_length=100, blank=True)
    google_sub = models.CharField(max_length=255, unique=True, null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        constraints = [
            models.UniqueConstraint(
                Lower("email"), name="user_email_case_insensitive_unique"
            ),
        ]


class WeeklyTarget(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="weekly_targets"
    )
    week_start = models.DateField()
    target_minutes = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "week_start"), name="unique_user_weekly_target"
            ),
            models.CheckConstraint(
                condition=Q(week_start__week_day=2),
                name="weekly_target_starts_monday",
            ),
        ]
        ordering = ("week_start",)

    def clean(self):
        super().clean()
        if self.week_start and self.week_start.weekday() != 0:
            raise ValidationError(
                {"week_start": _("The week start must be a Monday.")}
            )

    def __str__(self):
        return f"{self.user.email}: {self.week_start}"


class Shift(models.Model):
    class EntryMode(models.TextChoices):
        TIMED = "timed", _("Start and end time")
        DURATION = "duration", _("Total duration")

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="shifts")
    entry_mode = models.CharField(max_length=10, choices=EntryMode.choices)
    shift_date = models.DateField(null=True, blank=True)
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        entry_mode="timed",
                        shift_date__isnull=True,
                        start_at__isnull=False,
                        end_at__isnull=False,
                        duration_minutes__isnull=True,
                    )
                    & Q(end_at__gt=F("start_at"))
                )
                | Q(
                    entry_mode="duration",
                    shift_date__isnull=False,
                    start_at__isnull=True,
                    end_at__isnull=True,
                    duration_minutes__gt=0,
                ),
                name="shift_entry_matches_mode",
            ),
        ]
        indexes = [
            models.Index(fields=("user", "start_at")),
            models.Index(fields=("user", "shift_date")),
        ]
        ordering = ("start_at", "created_at")

    def __str__(self):
        return f"{self.user.email}: {self.entry_mode} shift"


class Break(models.Model):
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="breaks")
    duration_minutes = models.PositiveIntegerField()
    is_paid = models.BooleanField(default=False)
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(duration_minutes__gte=0),
                name="break_duration_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(start_at__isnull=True, end_at__isnull=True)
                    | Q(start_at__isnull=False, end_at__isnull=False)
                    & Q(end_at__gt=F("start_at"))
                ),
                name="break_timing_is_complete",
            ),
        ]
        ordering = ("start_at", "created_at")

    def __str__(self):
        return f"{self.duration_minutes} minute break"
