from django.db import transaction

from .models import Break, Shift, WeeklyTarget


def _save_breaks(shift, breaks):
    shift.breaks.all().delete()
    Break.objects.bulk_create(
        [Break(shift=shift, **break_data) for break_data in breaks]
    )


@transaction.atomic
def create_shift(*, user, validated_data):
    breaks = validated_data.pop("breaks", [])
    shift = Shift.objects.create(user=user, **validated_data)
    _save_breaks(shift, breaks)
    return shift


@transaction.atomic
def update_shift(*, shift, validated_data):
    breaks = validated_data.pop("breaks", None)
    for field, value in validated_data.items():
        setattr(shift, field, value)
    shift.save()
    if breaks is not None:
        _save_breaks(shift, breaks)
    return shift


@transaction.atomic
def delete_shift(*, shift):
    shift.delete()


@transaction.atomic
def set_weekly_target(*, user, week_start, target_minutes):
    target, _ = WeeklyTarget.objects.get_or_create(
        user=user,
        week_start=week_start,
        defaults={"target_minutes": target_minutes},
    )
    target.target_minutes = target_minutes
    target.full_clean()
    target.save(update_fields=("target_minutes", "updated_at"))
    return target
