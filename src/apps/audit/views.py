

from rest_framework import generics, permissions
from .models import AuditEvent
from .serializers import AuditEventSerializer

class AuditEventListView(generics.ListAPIView):
	queryset = AuditEvent.objects.all().order_by('-timestamp_server')
	serializer_class = AuditEventSerializer
	permission_classes = [permissions.IsAdminUser]
