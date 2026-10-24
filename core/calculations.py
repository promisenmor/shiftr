from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


LONDON = ZoneInfo("Europe/London")
UTC = timezone.utc


@dataclass(frozen=True)
class ShiftCalculation:
    gross_minutes: int
    paid_break_minutes: int
    unpaid_break_minutes: int
    net_minutes: int
    weekly_minutes: dict[date, int]


def _as_utc(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("Shift and break times must include a time zone.")
    if value.second or value.microsecond:
        raise ValueError("Shift and break times must have minute precision.")
    return value.astimezone(UTC)


def week_start_for(value):
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError("A shift time must include a time zone.")
        value = value.astimezone(LONDON).date()
    return value - timedelta(days=value.weekday())


def _week_end_utc(week_start):
    next_monday = week_start + timedelta(days=7)
    return datetime.combine(next_monday, time.min, tzinfo=LONDON).astimezone(UTC)


def allocate_interval(start_at, end_at):
    start = _as_utc(start_at)
    end = _as_utc(end_at)
    if end <= start:
        raise ValueError("The interval end must be after its start.")

    allocated = defaultdict(int)
    cursor = start
    while cursor < end:
        local_date = cursor.astimezone(LONDON).date()
        week_start = week_start_for(local_date)
        segment_end = min(end, _week_end_utc(week_start))
        minutes = int((segment_end - cursor).total_seconds() // 60)
        if minutes <= 0:
            raise ValueError("The interval could not be allocated to a working week.")
        allocated[week_start] += minutes
        cursor = segment_end
    return dict(allocated)


def _break_value(break_data, key, default=None):
    if isinstance(break_data, dict):
        return break_data.get(key, default)
    return getattr(break_data, key, default)


def calculate_shift(
    *,
    entry_mode,
    start_at=None,
    end_at=None,
    shift_date=None,
    duration_minutes=None,
    breaks=(),
):
    if entry_mode not in ("timed", "duration"):
        raise ValueError("The shift entry mode is invalid.")

    break_rows = list(breaks)
    break_items = []
    timed_breaks = []
    for break_data in break_rows:
        duration = _break_value(break_data, "duration_minutes")
        if not isinstance(duration, int) or isinstance(duration, bool) or duration < 0:
            raise ValueError("Break durations must be non-negative whole minutes.")
        is_paid = _break_value(break_data, "is_paid", False)
        if not isinstance(is_paid, bool):
            raise ValueError("Break paid status must be true or false.")
        break_start = _break_value(break_data, "start_at")
        break_end = _break_value(break_data, "end_at")
        if (break_start is None) != (break_end is None):
            raise ValueError("Provide both break start and end times.")
        if break_start is not None:
            if entry_mode != "timed":
                raise ValueError("Duration-only shifts cannot include timed breaks.")
            start_utc = _as_utc(break_start)
            end_utc = _as_utc(break_end)
            if end_utc <= start_utc:
                raise ValueError("A break must end after it starts.")
            elapsed_minutes = int((end_utc - start_utc).total_seconds() // 60)
            if elapsed_minutes != duration:
                raise ValueError("Break times must match the break duration.")
            timed_breaks.append((start_utc, end_utc))
        break_items.append((duration, is_paid, break_start, break_end))

    for index, (start, end) in enumerate(timed_breaks):
        for other_start, other_end in timed_breaks[index + 1 :]:
            if start < other_end and other_start < end:
                raise ValueError("Break times cannot overlap.")

    total_break_minutes = sum(duration for duration, _, _, _ in break_items)
    paid_break_minutes = sum(
        duration for duration, is_paid, _, _ in break_items if is_paid
    )
    unpaid_break_minutes = total_break_minutes - paid_break_minutes

    if entry_mode == "duration":
        if not isinstance(shift_date, date) or isinstance(shift_date, datetime):
            raise ValueError("A shift date is required for duration-only shifts.")
        if not isinstance(duration_minutes, int) or isinstance(duration_minutes, bool):
            raise ValueError("Shift duration must be a whole number of minutes.")
        if duration_minutes <= 0:
            raise ValueError("Shift duration must be greater than zero.")
        if any(start is not None for start, _ in timed_breaks):
            raise ValueError("Duration-only shifts cannot include timed breaks.")
        gross_minutes = duration_minutes
        allocated = {week_start_for(shift_date): gross_minutes}
    else:
        start = _as_utc(start_at)
        end = _as_utc(end_at)
        if end <= start:
            raise ValueError("A shift must end after it starts.")
        elapsed_seconds = (end - start).total_seconds()
        if elapsed_seconds % 60:
            raise ValueError("Shift duration must have minute precision.")
        gross_minutes = int(elapsed_seconds // 60)
        allocated = allocate_interval(start_at, end_at)

        for break_start, break_end in timed_breaks:
            if break_start < start or break_end > end:
                raise ValueError("Break times must fall within the shift.")

    if total_break_minutes > gross_minutes:
        raise ValueError("Break duration cannot exceed the shift duration.")

    weekly_unpaid = defaultdict(int)
    for duration, is_paid, break_start_at, break_end_at in break_items:
        if is_paid or duration == 0:
            continue
        if break_start_at is not None:
            for week, minutes in allocate_interval(
                break_start_at, break_end_at
            ).items():
                weekly_unpaid[week] += minutes
        else:
            if len(allocated) > 1:
                raise ValueError(
                    "Break times are required when an unpaid break could affect "
                    "allocation across working weeks."
                )
            week = next(iter(allocated))
            weekly_unpaid[week] += duration

    weekly_minutes = {}
    for week, gross in allocated.items():
        net = gross - weekly_unpaid[week]
        if net < 0:
            raise ValueError("Unpaid breaks cannot exceed work in a working week.")
        weekly_minutes[week] = net

    net_minutes = gross_minutes - unpaid_break_minutes
    if sum(weekly_minutes.values()) != net_minutes:
        raise ValueError(
            "Unpaid break timing must identify the working week for every deduction."
        )

    return ShiftCalculation(
        gross_minutes=gross_minutes,
        paid_break_minutes=paid_break_minutes,
        unpaid_break_minutes=unpaid_break_minutes,
        net_minutes=net_minutes,
        weekly_minutes=weekly_minutes,
    )


def summarize_week(week_start, target_minutes, shifts):
    worked_minutes = 0
    for shift in shifts:
        calculation = calculate_shift(
            entry_mode=shift.entry_mode,
            start_at=shift.start_at,
            end_at=shift.end_at,
            shift_date=shift.shift_date,
            duration_minutes=shift.duration_minutes,
            breaks=shift.breaks.all(),
        )
        worked_minutes += calculation.weekly_minutes.get(week_start, 0)

    target = target_minutes
    remaining_minutes = max(target - worked_minutes, 0) if target is not None else 0
    overtime_minutes = max(worked_minutes - target, 0) if target is not None else 0
    progress_percent = (
        0
        if target is None
        else (100 if target == 0 else min(round(worked_minutes * 100 / target), 100))
    )
    return {
        "week_start": week_start,
        "week_end": week_start + timedelta(days=6),
        "target_minutes": target,
        "worked_minutes": worked_minutes,
        "remaining_minutes": remaining_minutes,
        "overtime_minutes": overtime_minutes,
        "progress_percent": progress_percent,
    }
