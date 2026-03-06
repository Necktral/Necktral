from __future__ import annotations

from rest_framework.exceptions import APIException


class ConflictError(APIException):
    status_code = 409
    default_code = "CONFLICT"
    default_detail = "Conflicto."
