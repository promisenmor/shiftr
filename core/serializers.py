from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "display_name")
        read_only_fields = fields


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
