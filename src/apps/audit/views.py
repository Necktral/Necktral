

from django.core.exceptions import FieldDoesNotExist
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import CursorPagination

from apps.common.permissions import rbac_permission
from .models import AuditEvent
from .serializers import AuditEventListSerializer, AuditEventDetailSerializer
from .writer import _chain_partition_key

AuditReadPermission = rbac_permission("audit.read")

def _parse_bool(v: str | None):
	if v is None:
		return None
	v = v.strip().lower()
	if v in ("1", "true", "t", "yes", "y", "si"):
		return True
	if v in ("0", "false", "f", "no", "n"):
		return False
	return None

def _parse_dt(v: str | None):
	if not v:
		return None
	dt = parse_datetime(v)
	if dt:
		return dt if timezone.is_aware(dt) else timezone.make_aware(dt, timezone.get_current_timezone())
	d = parse_date(v)
	if d:
		dt2 = timezone.datetime.combine(d, timezone.datetime.min.time())
		return timezone.make_aware(dt2, timezone.get_current_timezone())
	return None

class AuditEventCursorPagination(CursorPagination):
	page_size = 50
	ordering = ("-timestamp_server", "-event_id")
	cursor_query_param = "cursor"
	page_size_query_param = "page_size"
	max_page_size = 200

class AuditEventListView(ListAPIView):
	permission_classes = [AuditReadPermission]
	pagination_class = AuditEventCursorPagination

	def get_serializer_class(self):
		include_integrity = _parse_bool(self.request.query_params.get("include_integrity"))
		return AuditEventDetailSerializer if include_integrity else AuditEventListSerializer

	def get_queryset(self):
		qs = AuditEvent.objects.all().select_related("actor_user")
		partition_key = _chain_partition_key(self.request)
		try:
			AuditEvent._meta.get_field("partition_key")
			qs = qs.filter(partition_key=partition_key)
		except FieldDoesNotExist:
			qs = qs.filter(metadata__contains={"_chain_partition": partition_key})

		qp = self.request.query_params
		if qp.get("event_type"):
			qs = qs.filter(event_type=qp["event_type"])
		if qp.get("reason_code"):
			qs = qs.filter(reason_code=qp["reason_code"])
		if qp.get("module"):
			qs = qs.filter(module=qp["module"])
		if qp.get("method"):
			qs = qs.filter(method=qp["method"])
		if qp.get("device_id"):
			qs = qs.filter(device_id=qp["device_id"])
		if qp.get("subject_type"):
			qs = qs.filter(subject_type=qp["subject_type"])
		if qp.get("subject_id"):
			qs = qs.filter(subject_id=qp["subject_id"])
		if qp.get("actor_user_id"):
			try:
				qs = qs.filter(actor_user_id=int(qp["actor_user_id"]))
			except ValueError:
				pass
		offline_mode = _parse_bool(qp.get("offline_mode"))
		if offline_mode is not None:
			qs = qs.filter(offline_mode=offline_mode)
		if qp.get("path_contains"):
			qs = qs.filter(path__icontains=qp["path_contains"])
		if qp.get("ip"):
			qs = qs.filter(ip_server_seen=qp["ip"])
		after = _parse_dt(qp.get("after") or qp.get("start"))
		before = _parse_dt(qp.get("before") or qp.get("end"))
		if after:
			qs = qs.filter(timestamp_server__gte=after)
		if before:
			qs = qs.filter(timestamp_server__lte=before)
		return qs.order_by("-timestamp_server", "-event_id")

class AuditEventDetailView(RetrieveAPIView):
	permission_classes = [AuditReadPermission]
	serializer_class = AuditEventDetailSerializer
	lookup_field = "event_id"
	lookup_url_kwarg = "event_id"

	def get_queryset(self):
		qs = AuditEvent.objects.all().select_related("actor_user")
		partition_key = _chain_partition_key(self.request)
		try:
			AuditEvent._meta.get_field("partition_key")
			return qs.filter(partition_key=partition_key)
		except FieldDoesNotExist:
			return qs.filter(metadata__contains={"_chain_partition": partition_key})
