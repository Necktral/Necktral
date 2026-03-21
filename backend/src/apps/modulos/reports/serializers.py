from __future__ import annotations

from django.core.validators import RegexValidator
from rest_framework import serializers


_CODE_VALIDATOR = RegexValidator(
    regex=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$",
    message="invalid_code",
)


class ReportDefinitionCreateIn(serializers.Serializer):
    code = serializers.CharField(max_length=64, validators=[_CODE_VALIDATOR])
    name = serializers.CharField(max_length=160)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    schema_version = serializers.IntegerField(required=False, default=1, min_value=1)
    contract_version = serializers.IntegerField(required=False, default=1, min_value=1)
    is_active = serializers.BooleanField(required=False, default=True)


class ReportRunCreateIn(serializers.Serializer):
    code = serializers.CharField(max_length=64, validators=[_CODE_VALIDATOR])
    params = serializers.DictField(required=False, default=dict)
    parameters = serializers.DictField(required=False, default=dict)
    as_of = serializers.DateTimeField(required=False, allow_null=True)
    time_window = serializers.DictField(required=False, default=dict)
    format = serializers.CharField(required=False, allow_blank=True, default="json")
    run_async = serializers.BooleanField(required=False, default=False)
    priority = serializers.IntegerField(required=False, default=5, min_value=1, max_value=10)
    use_cache = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        if "params" in attrs and "parameters" in attrs:
            p1 = attrs.get("params") or {}
            p2 = attrs.get("parameters") or {}
            if p1 and p2 and p1 != p2:
                raise serializers.ValidationError({"params": ["conflicts with parameters"]})
        params = dict(attrs.get("params") or attrs.get("parameters") or {})
        analytics_keys = {"filters", "group_by", "metrics", "sort", "cursor", "comparison", "drill_path"}
        if analytics_keys.intersection(params.keys()):
            filters = params.get("filters")
            group_by = params.get("group_by")
            metrics = params.get("metrics")
            sort = params.get("sort")
            drill_path = params.get("drill_path")
            if filters is not None and not isinstance(filters, dict):
                raise serializers.ValidationError({"params": ["filters must be object"]})
            if group_by is not None and not isinstance(group_by, list):
                raise serializers.ValidationError({"params": ["group_by must be list"]})
            if metrics is not None and not isinstance(metrics, list):
                raise serializers.ValidationError({"params": ["metrics must be list"]})
            if sort is not None and not isinstance(sort, list):
                raise serializers.ValidationError({"params": ["sort must be list"]})
            if drill_path is not None and not isinstance(drill_path, list):
                raise serializers.ValidationError({"params": ["drill_path must be list"]})
            if isinstance(group_by, list) and len(group_by) > 12:
                raise serializers.ValidationError({"params": ["group_by max length is 12"]})
            if isinstance(metrics, list) and len(metrics) > 24:
                raise serializers.ValidationError({"params": ["metrics max length is 24"]})
            if isinstance(drill_path, list) and len(drill_path) > 12:
                raise serializers.ValidationError({"params": ["drill_path max length is 12"]})
        return attrs


class ReportExportCreateIn(serializers.Serializer):
    execution_id = serializers.UUIDField()
    format = serializers.ChoiceField(choices=["json", "jsonl", "csv", "xlsx", "pdf"], default="json")
    template_version = serializers.CharField(max_length=32, required=False, allow_blank=True, default="v1")
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    require_dual_approval = serializers.BooleanField(required=False, default=False)
    approved_by_user_id = serializers.IntegerField(required=False, allow_null=True)
