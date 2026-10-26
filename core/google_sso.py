from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction


class GoogleAccountConflict(Exception):
    pass


def get_or_create_google_user(*, subject, email, display_name=""):
    user_model = get_user_model()
    normalized_email = user_model.objects.normalize_email(email).lower()
    try:
        user_model._meta.get_field("email").clean(normalized_email, None)
    except DjangoValidationError as error:
        raise GoogleAccountConflict("Google returned an invalid email address.") from error

    try:
        with transaction.atomic():
            user = user_model.objects.filter(google_sub=subject).first()
            if user:
                if not user.is_active:
                    raise GoogleAccountConflict("This account is disabled.")
                return user

            user = user_model.objects.filter(email__iexact=normalized_email).first()
            if user:
                if not user.is_active:
                    raise GoogleAccountConflict("This account is disabled.")
                if user.google_sub and user.google_sub != subject:
                    raise GoogleAccountConflict(
                        "This email is linked to a different Google account."
                    )
                user.google_sub = subject
                user.save(update_fields=("google_sub",))
                return user

            return user_model.objects.create_user(
                email=normalized_email,
                password=None,
                display_name=display_name[:100],
                google_sub=subject,
            )
    except IntegrityError as error:
        raise GoogleAccountConflict(
            "This Google account could not be linked. Please try again."
        ) from error
