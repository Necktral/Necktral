from __future__ import annotations

from rest_framework import serializers


class WorkspaceQueryIn(serializers.Serializer):
    widget_code = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    filters = serializers.DictField(required=False, default=dict)
    group_by = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list)
    metrics = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list)
    sort = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    cursor = serializers.JSONField(required=False, default=dict)
    comparison = serializers.DictField(required=False, default=dict)
    drill_path = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list)
    time_window = serializers.DictField(required=False, default=dict)
    as_of = serializers.DateTimeField(required=False, allow_null=True)
    run_async = serializers.BooleanField(required=False, default=False)
    priority = serializers.IntegerField(required=False, default=5, min_value=1, max_value=10)
    use_cache = serializers.BooleanField(required=False, default=True)
    company_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, default=list)
    branch_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)

    def validate(self, attrs):
        group_by = list(attrs.get("group_by") or [])
        metrics = list(attrs.get("metrics") or [])
        drill_path = list(attrs.get("drill_path") or [])
        if len(group_by) > 12:
            raise serializers.ValidationError({"group_by": ["max 12 fields"]})
        if len(metrics) > 24:
            raise serializers.ValidationError({"metrics": ["max 24 fields"]})
        if len(drill_path) > 10:
            raise serializers.ValidationError({"drill_path": ["max 10 segments"]})
        return attrs


class DashboardDrilldownIn(serializers.Serializer):
    workspace_code = serializers.CharField(max_length=64)
    widget_code = serializers.CharField(max_length=64)
    drill_path = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list)
    filters = serializers.DictField(required=False, default=dict)
    group_by = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list)
    metrics = serializers.ListField(child=serializers.CharField(max_length=64), required=False, default=list)
    sort = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    cursor = serializers.JSONField(required=False, default=dict)
    comparison = serializers.DictField(required=False, default=dict)
    company_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, default=list)
    branch_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)

    def validate(self, attrs):
        drill_path = list(attrs.get("drill_path") or [])
        if len(drill_path) > 12:
            raise serializers.ValidationError({"drill_path": ["max 12 segments"]})
        return attrs
