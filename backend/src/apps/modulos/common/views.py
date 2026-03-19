from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.metrics import snapshot


class MetricsView(APIView):
	permission_classes = [IsAuthenticated]
	throttle_scope = "heavy_reads"

	def get(self, request):
		user = request.user
		if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
			return Response({"detail": "No autorizado."}, status=403)
		return Response(snapshot(), status=200)
