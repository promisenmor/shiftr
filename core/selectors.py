from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from .calculations import LONDON
from .models import Shift, WeeklyTarget


def _week_boundary(day):
    return timezone.make_aware(datetime.combine(day, time.min), LONDON)


def shifts_for_user(user, *, start_date=None, end_date=None):
    shifts = Shift.objects.filter(user=user).prefetch_related("breaks")
    if start_date is not None:
        start_boundary = _week_boundary(start_date)
        shifts = shifts.filter(
            Q(entry_mode=Shift.EntryMode.TIMED, end_at__gt=start_boundary)
            | Q(entry_mode=Shift.EntryMode.DURATION, shift_date__gte=start_date)
        )
    if end_date is not None:
        end_boundary = _week_boundary(end_date + timedelta(days=1))
        shifts = shifts.filter(
            Q(entry_mode=Shift.EntryMode.TIMED, start_at__lt=end_boundary)
            | Q(entry_mode=Shift.EntryMode.DURATION, shift_date__lte=end_date)
        )
    return shifts.order_by("start_at", "shift_date", "created_at")


def shifts_for_week(user, week_start):
    return shifts_for_user(
        user,
        start_date=week_start,
        end_date=week_start + timedelta(days=6),
    )


def weekly_targets_for_user(user):
    return WeeklyTarget.objects.filter(user=user).order_by("week_start")


def weekly_summary_for_user(user, week_start):
    from .calculations import summarize_week

    shifts = list(shifts_for_week(user, week_start))
    target = WeeklyTarget.objects.filter(user=user, week_start=week_start).first()
    previous_target = (
        WeeklyTarget.objects.filter(user=user, week_start__lt=week_start)
        .order_by("-week_start")
        .first()
    )
    summary = summarize_week(
        week_start,
        target.target_minutes if target else None,
        shifts,
    )
    summary["suggested_target_minutes"] = (
        previous_target.target_minutes if previous_target else None
    )
    summary["target_is_set"] = target is not None
    summary["shifts"] = shifts
    return summary
