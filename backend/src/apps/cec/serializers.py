from __future__ import annotations

from rest_framework import serializers

from .models import CECException, CloseRun


class CloseRunCreateIn(serializers.Serializer):
    run_type = serializers.ChoiceField(choices=CloseRun.RunType.choices, required=False)
    branch_id = serializers.IntegerField(required=False)
    input_manifest_hash = serializers.CharField(max_length=64, required=False, allow_blank=True)


class CloseRunAdvanceIn(serializers.Serializer):
    status = serializers.ChoiceField(choices=CloseRun.Status.choices)
    output_manifest_hash = serializers.CharField(max_length=64, required=False, allow_blank=True)
    summary_json = serializers.JSONField(required=False)


class CloseRunExecuteIn(serializers.Serializer):
    window_start = serializers.DateTimeField()
    window_end = serializers.DateTimeField()
    strict = serializers.BooleanField(required=False, default=True)


class CECExceptionCreateIn(serializers.Serializer):
    source_module = serializers.CharField(max_length=64)
    code = serializers.CharField(max_length=64)
    severity = serializers.ChoiceField(choices=CECException.Severity.choices, required=False)
    related_object_type = serializers.CharField(max_length=64, required=False, allow_blank=True)
    related_object_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    details_json = serializers.JSONField(required=False)
    close_run_id = serializers.UUIDField(required=False)


class CECExceptionResolveIn(serializers.Serializer):
    resolution_note = serializers.CharField(required=False, allow_blank=True)


class EvidenceCreateIn(serializers.Serializer):
    support_id = serializers.CharField(max_length=96)
    sha256 = serializers.RegexField(regex=r"^[a-fA-F0-9]{64}$")
    mime_type = serializers.CharField(max_length=64)
    storage_ref = serializers.CharField(max_length=255)
    metadata_json = serializers.JSONField(required=False)
    close_run_id = serializers.UUIDField(required=False)
