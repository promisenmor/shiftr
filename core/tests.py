from datetime import date, datetime, timezone

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import Shift, WeeklyTarget


User = get_user_model()


class AuthenticationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="worker@example.com",
            password="C0mpl3x-Weekly-Shift!",
            display_name="Worker",
        )

    def test_registration_creates_email_user_and_returns_token(self):
        response = self.client.post(
            reverse("register"),
            {
                "email": " New.Worker@Example.com ",
                "password": "V3ry-Secure-Password!",
                "display_name": "New Worker",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["email"], "new.worker@example.com")
        self.assertTrue(
            Token.objects.filter(
                key=response.data["token"],
                user__email="new.worker@example.com",
            ).exists()
        )

    def test_registration_rejects_duplicate_email_and_weak_password(self):
        duplicate = self.client.post(
            reverse("register"),
            {"email": self.user.email, "password": "V3ry-Secure-Password!"},
        )
        weak_password = self.client.post(
            reverse("register"),
            {"email": "other@example.com", "password": "password"},
        )

        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(weak_password.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_rejects_invalid_credentials_without_account_disclosure(self):
        response = self.client.post(
            reverse("login"),
            {"email": self.user.email, "password": "incorrect-password"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            str(response.data["non_field_errors"][0]), "Invalid email or password."
        )

    def test_login_and_logout_issue_and_revoke_token(self):
        response = self.client.post(
            reverse("login"),
            {"email": self.user.email.upper(), "password": "C0mpl3x-Weekly-Shift!"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        token = response.data["token"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        logout_response = self.client.post(reverse("logout"))

        self.assertEqual(logout_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Token.objects.filter(key=token).exists())
        profile_response = self.client.get(reverse("profile"))
        self.assertEqual(profile_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profile_is_authenticated_and_updates_only_current_user(self):
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.patch(
            reverse("profile"), {"display_name": "Updated name"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "Updated name")
        self.assertEqual(response.data["email"], self.user.email)


class DomainModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="worker@example.com", password="C0mpl3x-Weekly-Shift!"
        )

    def test_weekly_target_requires_monday_and_is_unique_per_user_week(self):
        target = WeeklyTarget(
            user=self.user,
            week_start=date(2026, 10, 19),
            target_minutes=1200,
        )
        target.full_clean()
        target.save()

        duplicate = WeeklyTarget(
            user=self.user,
            week_start=date(2026, 10, 19),
            target_minutes=900,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            duplicate.save()

        invalid_week = WeeklyTarget(
            user=self.user,
            week_start=date(2026, 10, 20),
            target_minutes=1200,
        )
        with self.assertRaises(ValidationError):
            invalid_week.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            invalid_week.save()

    def test_email_uniqueness_is_case_insensitive_at_database_level(self):
        duplicate = User(email=self.user.email.upper())
        duplicate.set_password("C0mpl3x-Weekly-Shift!")

        with self.assertRaises(IntegrityError), transaction.atomic():
            duplicate.save()

    def test_shift_database_constraint_enforces_entry_mode_fields(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Shift.objects.create(
                user=self.user,
                entry_mode=Shift.EntryMode.TIMED,
                duration_minutes=480,
            )

        timed_shift = Shift.objects.create(
            user=self.user,
            entry_mode=Shift.EntryMode.TIMED,
            start_at=datetime(2026, 10, 19, 9, tzinfo=timezone.utc),
            end_at=datetime(2026, 10, 19, 17, tzinfo=timezone.utc),
        )
        self.assertEqual(timed_shift.entry_mode, Shift.EntryMode.TIMED)
