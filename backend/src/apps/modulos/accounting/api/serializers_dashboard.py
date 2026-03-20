from __future__ import annotations

from rest_framework import serializers


class DashboardRangeIn(serializers.Serializer):
    year = serializers.IntegerField(required=False, min_value=2000, max_value=2100)
    month = serializers.IntegerField(required=False, min_value=1, max_value=12)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    as_of = serializers.DateField(required=False)
    months = serializers.IntegerField(required=False, min_value=1, max_value=24)
    refresh = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        year = attrs.get("year")
        month = attrs.get("month")
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")
        as_of = attrs.get("as_of")
        if (year is None) != (month is None):
            raise serializers.ValidationError("year y month deben enviarse juntos.")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError("date_from debe ser menor o igual que date_to.")
        if as_of and (date_from or date_to):
            raise serializers.ValidationError("as_of no puede combinarse con date_from/date_to.")
        return attrs

