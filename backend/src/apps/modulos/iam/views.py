from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.audit.writer import write_event

from .bootstrap_services import bootstrap_init_admin, get_bootstrap_status
from .serializers import BootstrapInitAdminSerializer


class ContextEchoView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "context_read"

    def get(self, request):
        company = getattr(request, "company", None)
        branch = getattr(request, "branch", None)
        return Response(
            {
                "company_id": getattr(company, "id", None),
                "branch_id": getattr(branch, "id", None),
            }
        )


class BootstrapStatusView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "heavy_reads"

    def get(self, request):
        return Response(get_bootstrap_status(), status=status.HTTP_200_OK)


class BootstrapInitAdminView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "admin_writes"

    def post(self, request):
        serializer = BootstrapInitAdminSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = bootstrap_init_admin(serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        write_event(
            request=request,
            event_type="AUTH_BOOTSTRAP_ADMIN_CREATED",
            reason_code="OK",
            actor_user=user,
            subject_type="USER",
            subject_id=str(user.id),
            metadata={"username": user.username},
        )
        return Response({"id": user.id}, status=status.HTTP_201_CREATED)
