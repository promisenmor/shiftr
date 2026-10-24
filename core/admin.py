from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserCreationForm

from .models import Break, Shift, User, WeeklyTarget


class EmailUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "display_name")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = EmailUserCreationForm
    ordering = ("email",)
    list_display = ("email", "display_name", "is_staff", "is_active")
    search_fields = ("email", "display_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("display_name", "first_name", "last_name")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "display_name", "password1", "password2"),
            },
        ),
    )


admin.site.register((WeeklyTarget, Shift, Break))
