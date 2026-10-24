from datetime import date, datetime, timezone
from unittest import TestCase

from .calculations import allocate_interval, calculate_shift, summarize_week


class ShiftCalculationTests(TestCase):
    def test_zero_minute_break_is_valid_and_negative_break_is_invalid(self):
        result = calculate_shift(
            entry_mode="timed",
            start_at=datetime(2026, 10, 19, 9, tzinfo=timezone.utc),
            end_at=datetime(2026, 10, 19, 17, tzinfo=timezone.utc),
            breaks=[{"duration_minutes": 0, "is_paid": False}],
        )

        self.assertEqual(result.net_minutes, 480)
        with self.assertRaisesRegex(ValueError, "non-negative"):
            calculate_shift(
                entry_mode="timed",
                start_at=datetime(2026, 10, 19, 9, tzinfo=timezone.utc),
                end_at=datetime(2026, 10, 19, 17, tzinfo=timezone.utc),
                breaks=[{"duration_minutes": -1, "is_paid": False}],
            )

    def test_unpaid_break_is_deducted_and_paid_break_is_counted(self):
        start = datetime(2026, 10, 19, 9, tzinfo=timezone.utc)
        end = datetime(2026, 10, 19, 17, tzinfo=timezone.utc)

        unpaid = calculate_shift(
            entry_mode="timed",
            start_at=start,
            end_at=end,
            breaks=[{"duration_minutes": 30, "is_paid": False}],
        )
        paid = calculate_shift(
            entry_mode="timed",
            start_at=start,
            end_at=end,
            breaks=[{"duration_minutes": 30, "is_paid": True}],
        )

        self.assertEqual(unpaid.gross_minutes, 480)
        self.assertEqual(unpaid.net_minutes, 450)
        self.assertEqual(paid.net_minutes, 480)

    def test_overnight_shift_allocates_work_to_each_week(self):
        result = calculate_shift(
            entry_mode="timed",
            start_at=datetime(2026, 10, 25, 22, tzinfo=timezone.utc),
            end_at=datetime(2026, 10, 26, 6, tzinfo=timezone.utc),
        )

        self.assertEqual(
            result.weekly_minutes,
            {date(2026, 10, 19): 120, date(2026, 10, 26): 360},
        )

    def test_timed_break_crossing_week_boundary_is_split(self):
        result = calculate_shift(
            entry_mode="timed",
            start_at=datetime(2026, 10, 25, 22, tzinfo=timezone.utc),
            end_at=datetime(2026, 10, 26, 6, tzinfo=timezone.utc),
            breaks=[
                {
                    "duration_minutes": 60,
                    "is_paid": False,
                    "start_at": datetime(2026, 10, 25, 23, 30, tzinfo=timezone.utc),
                    "end_at": datetime(2026, 10, 26, 0, 30, tzinfo=timezone.utc),
                }
            ],
        )

        self.assertEqual(
            result.weekly_minutes,
            {date(2026, 10, 19): 90, date(2026, 10, 26): 330},
        )

    def test_untimed_unpaid_break_is_rejected_when_shift_crosses_week(self):
        with self.assertRaisesRegex(ValueError, "Break times are required"):
            calculate_shift(
                entry_mode="timed",
                start_at=datetime(2026, 10, 25, 22, tzinfo=timezone.utc),
                end_at=datetime(2026, 10, 26, 6, tzinfo=timezone.utc),
                breaks=[{"duration_minutes": 30, "is_paid": False}],
            )

    def test_daylight_saving_transitions_use_elapsed_time(self):
        spring_forward = allocate_interval(
            datetime(2026, 3, 29, 0, 30, tzinfo=timezone.utc),
            datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc),
        )
        autumn_back = allocate_interval(
            datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc),
            datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(sum(spring_forward.values()), 60)
        self.assertEqual(sum(autumn_back.values()), 60)

    def test_invalid_durations_excessive_breaks_and_overlapping_breaks_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            calculate_shift(
                entry_mode="duration",
                shift_date=date(2026, 10, 19),
                duration_minutes=0,
            )

        start = datetime(2026, 10, 19, 9, tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            calculate_shift(
                entry_mode="timed",
                start_at=start,
                end_at=datetime(2026, 10, 19, 17, tzinfo=timezone.utc),
                breaks=[{"duration_minutes": 481, "is_paid": False}],
            )

        with self.assertRaisesRegex(ValueError, "cannot overlap"):
            calculate_shift(
                entry_mode="timed",
                start_at=start,
                end_at=datetime(2026, 10, 19, 17, tzinfo=timezone.utc),
                breaks=[
                    {
                        "duration_minutes": 30,
                        "is_paid": False,
                        "start_at": datetime(2026, 10, 19, 11, tzinfo=timezone.utc),
                        "end_at": datetime(2026, 10, 19, 11, 30, tzinfo=timezone.utc),
                    },
                    {
                        "duration_minutes": 30,
                        "is_paid": False,
                        "start_at": datetime(2026, 10, 19, 11, 15, tzinfo=timezone.utc),
                        "end_at": datetime(2026, 10, 19, 11, 45, tzinfo=timezone.utc),
                    },
                ],
            )


class WeeklySummaryCalculationTests(TestCase):
    def test_remaining_time_is_never_negative_and_overtime_is_separate(self):
        class ShiftStub:
            entry_mode = "duration"
            shift_date = date(2026, 10, 19)
            duration_minutes = 600
            start_at = None
            end_at = None

            class Breaks:
                @staticmethod
                def all():
                    return []

            breaks = Breaks()

        result = summarize_week(date(2026, 10, 19), 480, [ShiftStub()])

        self.assertEqual(result["remaining_minutes"], 0)
        self.assertEqual(result["overtime_minutes"], 120)
        self.assertEqual(result["progress_percent"], 100)

    def test_zero_target_is_complete_without_producing_negative_remaining_time(self):
        result = summarize_week(date(2026, 10, 19), 0, [])

        self.assertEqual(result["remaining_minutes"], 0)
        self.assertEqual(result["overtime_minutes"], 0)
        self.assertEqual(result["progress_percent"], 100)
