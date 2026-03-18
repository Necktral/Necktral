from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class PasswordComplexityValidator:
    def __init__(self, min_length: int = 10, min_classes: int = 3) -> None:
        self.min_length = int(min_length)
        self.min_classes = int(min_classes)

    def validate(self, password: str, user=None) -> None:
        if len(password) < self.min_length:
            raise ValidationError(
                _(f"La contraseña debe tener al menos {self.min_length} caracteres."),
                code="password_too_short",
            )

        classes = 0
        if any(c.islower() for c in password):
            classes += 1
        if any(c.isupper() for c in password):
            classes += 1
        if any(c.isdigit() for c in password):
            classes += 1
        if any(not c.isalnum() for c in password):
            classes += 1

        if classes < self.min_classes:
            raise ValidationError(
                _(
                    "La contraseña debe incluir al menos "
                    f"{self.min_classes} de: minusculas, mayusculas, numeros, simbolos."
                ),
                code="password_not_complex_enough",
            )

    def get_help_text(self) -> str:
        return (
            "Tu contraseña debe tener al menos "
            f"{self.min_length} caracteres y "
            f"{self.min_classes} clases (minusculas, mayusculas, numeros, simbolos)."
        )
