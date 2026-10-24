from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from .models import Shift


User = get_user_model()


class ShiftApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="worker@example.com",
            password="C0mpl3x-Weekly-Shift!",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="C0mpl3x-Weekly-Shift!",
        )
        self.client.force_authenticate(user=self.user)

    def create_overnight_shift(self):
        response = self.client.post(
            reverse("shift-list"),
            {
                "entry_mode": "timed",
                "start_at": "2026-10-25T22:00:00+00:00",
                "end_at": "2026-10-26T06:00:00+00:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data["id"]

    def test_timed_shift_and_paid_or_unpaid_break_calculations(self):
        unpaid = self.client.post(
            reverse("shift-list"),
            {
                "entry_mode": "timed",
                "start_at": "2026-10-19T09:00:00+01:00",
                "end_at": "2026-10-19T17:00:00+01:00",
                "breaks": [{"duration_minutes": 30, "is_paid": False}],
            },
            format="json",
        )
        paid = self.client.post(
            reverse("shift-list"),
            {
                "entry_mode": "timed",
                "start_at": "2026-10-20T09:00:00+01:00",
                "end_at": "2026-10-20T17:00:00+01:00",
                "breaks": [{"duration_minutes": 30, "is_paid": True}],
            },
            format="json",
        )

        self.assertEqual(unpaid.status_code, status.HTTP_201_CREATED, unpaid.data)
        self.assertEqual(unpaid.data["net_minutes"], 450)
        self.assertEqual(unpaid.json()["weekly_allocations"], [
            {"week_start": "2026-10-19", "minutes": 450}
        ])
        self.assertEqual(paid.status_code, status.HTTP_201_CREATED, paid.data)
        self.assertEqual(paid.data["net_minutes"], 480)

    def test_duration_entry_is_allocated_to_selected_date_week(self):
        response = self.client.post(
            reverse("shift-list"),
            {
                "entry_mode": "duration",
                "shift_date": "2026-10-21",
                "duration_minutes": 480,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["net_minutes"], 480)
        self.assertEqual(response.json()["weekly_allocations"], [
            {"week_start": "2026-10-19", "minutes": 480}
        ])

    def test_shift_validation_rejects_invalid_durations_and_dst_wall_times(self):
        invalid_duration = self.client.post(
            reverse("shift-list"),
            {
                "entry_mode": "duration",
                "shift_date": "2026-10-21",
                "duration_minutes": 0,
            },
            format="json",
        )
        ambiguous_time = self.client.post(
            reverse("shift-list"),
            {
                "entry_mode": "timed",
                "start_at": "2026-10-25T01:30:00",
                "end_at": "2026-10-25T02:30:00",
            },
            format="json",
        )
        nonexistent_time = self.client.post(
            reverse("shift-list"),
            {
                "entry_mode": "timed",
                "start_at": "2026-03-29T01:30:00",
                "end_at": "2026-03-29T02:30:00",
            },
            format="json",
        )

        self.assertEqual(invalid_duration.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ambiguous_time.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(nonexistent_time.status_code, status.HTTP_400_BAD_REQUEST)

    def test_weekly_allocation_and_edit_delete_recalculate_both_weeks(self):
        shift_id = self.create_overnight_shift()
        previous_summary_url = reverse(
            "weekly-summary", kwargs={"week_start": "2026-10-19"}
        )
        next_summary_url = reverse(
            "weekly-summary", kwargs={"week_start": "2026-10-26"}
        )
        previous_summary = self.client.get(previous_summary_url)
        next_summary = self.client.get(next_summary_url)

        self.assertEqual(previous_summary.data["worked_minutes"], 120)
        self.assertEqual(next_summary.data["worked_minutes"], 360)

        update = self.client.patch(
            reverse("shift-detail", kwargs={"pk": shift_id}),
            {"end_at": "2026-10-26T07:00:00+00:00"},
            format="json",
        )
        self.assertEqual(update.status_code, status.HTTP_200_OK, update.data)
        self.assertEqual(
            self.client.get(next_summary_url).data["worked_minutes"], 420
        )

        delete = self.client.delete(reverse("shift-detail", kwargs={"pk": shift_id}))
        self.assertEqual(delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            self.client.get(previous_summary_url).data["worked_minutes"], 0
        )
        self.assertEqual(self.client.get(next_summary_url).data["worked_minutes"], 0)

    def test_week_boundary_break_requires_timing_and_is_allocated_exactly(self):
        missing_timing = self.client.post(
            reverse("shift-list"),
            {
                "entry_mode": "timed",
                "start_at": "2026-10-25T22:00:00+00:00",
                "end_at": "2026-10-26T06:00:00+00:00",
                "breaks": [{"duration_minutes": 60, "is_paid": False}],
            },
            format="json",
        )
        with_timing = self.client.post(
            reverse("shift-list"),
            {
                "entry_mode": "timed",
                "start_at": "2026-10-25T22:00:00+00:00",
                "end_at": "2026-10-26T06:00:00+00:00",
                "breaks": [
                    {
                        "duration_minutes": 60,
                        "is_paid": False,
                        "start_at": "2026-10-25T23:30:00+00:00",
                        "end_at": "2026-10-26T00:30:00+00:00",
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(missing_timing.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(with_timing.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            with_timing.json()["weekly_allocations"],
            [
                {"week_start": "2026-10-19", "minutes": 90},
                {"week_start": "2026-10-26", "minutes": 330},
            ],
        )

    def test_shifts_and_targets_are_private_to_the_authenticated_user(self):
        shift_id = self.create_overnight_shift()
        self.client.force_authenticate(user=self.other_user)

        self.assertEqual(self.client.get(reverse("shift-list")).data, [])
        self.assertEqual(
            self.client.get(reverse("shift-detail", kwargs={"pk": shift_id})).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(self.client.get(reverse("weekly-target-list")).data, [])

    def test_weekly_targets_are_week_specific_and_overtime_is_separate(self):
        self.client.put(
            reverse(
                "weekly-target-detail",
                kwargs={"week_start": "2026-10-19"},
            ),
            {"target_minutes": 300},
            format="json",
        )
        self.create_overnight_shift()
        next_target = self.client.put(
            reverse(
                "weekly-target-detail",
                kwargs={"week_start": "2026-10-26"},
            ),
            {"target_minutes": 240},
            format="json",
        )
        previous_summary = self.client.get(
            reverse("weekly-summary", kwargs={"week_start": "2026-10-19"})
        )
        next_summary = self.client.get(
            reverse("weekly-summary", kwargs={"week_start": "2026-10-26"})
        )

        self.assertEqual(next_target.status_code, status.HTTP_200_OK)
        self.assertEqual(previous_summary.data["target_minutes"], 300)
        self.assertEqual(previous_summary.data["remaining_minutes"], 180)
        self.assertEqual(next_summary.data["target_minutes"], 240)
        self.assertEqual(next_summary.data["remaining_minutes"], 0)
        self.assertEqual(next_summary.data["overtime_minutes"], 120)
        self.assertEqual(next_summary.data["suggested_target_minutes"], 300)

        changed_target = self.client.put(
            reverse(
                "weekly-target-detail",
                kwargs={"week_start": "2026-10-26"},
            ),
            {"target_minutes": 480},
            format="json",
        )
        self.assertEqual(changed_target.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.get(
                reverse("weekly-summary", kwargs={"week_start": "2026-10-19"})
            ).data["target_minutes"],
            300,
        )
        updated_summary = self.client.get(
            reverse("weekly-summary", kwargs={"week_start": "2026-10-26"})
        )
        self.assertEqual(updated_summary.data["remaining_minutes"], 120)
        self.assertEqual(updated_summary.data["overtime_minutes"], 0)

    def test_non_monday_target_and_summary_dates_are_rejected(self):
        target = self.client.put(
            reverse("weekly-target-detail", kwargs={"week_start": "2026-10-20"}),
            {"target_minutes": 300},
            format="json",
        )
        summary = self.client.get(
            reverse("weekly-summary", kwargs={"week_start": "2026-10-20"})
        )

        self.assertEqual(target.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(summary.status_code, status.HTTP_400_BAD_REQUEST)

    def test_swagger_ui_and_openapi_schema_are_available(self):
        public_client = APIClient()
        schema = public_client.get(reverse("schema"))
        swagger = public_client.get(reverse("swagger-ui"))

        self.assertEqual(schema.status_code, status.HTTP_200_OK)
        self.assertEqual(swagger.status_code, status.HTTP_200_OK)
        self.assertIn("/api/shifts/", schema.data["paths"])
        self.assertIn("/api/weeks/{week_start}/summary/", schema.data["paths"])
        self.assertIn("jwtAuth", schema.data["components"]["securitySchemes"])
        self.assertIn("swagger-ui", swagger.content.decode())
