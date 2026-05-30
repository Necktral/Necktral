from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission

from .models import Party, PartyRole
from .serializers import (
    PartyCreateSerializer,
    PartyListSerializer,
    PartyRoleAssignSerializer,
    PartyRoleRevokeSerializer,
    PartyRoleSerializer,
    PartyUpdateSerializer,
)
from .services import assign_party_role, create_party, revoke_party_role, update_party


def _validation_error_detail(exc: DjangoValidationError) -> dict | str:
    """Extract safe error messages from DjangoValidationError without exposing stack traces."""
    if hasattr(exc, "message_dict"):
        return exc.message_dict
    if hasattr(exc, "messages"):
        return {"non_field_errors": exc.messages}
    return {"non_field_errors": [str(exc.message)]}


class PartyListCreateView(APIView):
    """
    GET  /api/parties/          — Listar parties de la company activa.
    POST /api/parties/          — Crear party en la company activa.
    """

    permission_classes = [rbac_permission("parties.read")]
    throttle_scope = "heavy_reads"

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("parties.write")()]
        return super().get_permissions()

    def get(self, request):
        company = getattr(request, "company", None)
        if company is None:
            return Response({"detail": "Company context required."}, status=status.HTTP_400_BAD_REQUEST)

        qs = Party.objects.filter(company=company).prefetch_related("roles").order_by("-created_at")

        # Filtros opcionales
        party_type = request.query_params.get("party_type")
        if party_type:
            qs = qs.filter(party_type=party_type)

        party_status = request.query_params.get("status")
        if party_status:
            qs = qs.filter(status=party_status)

        role_filter = request.query_params.get("role")
        if role_filter:
            qs = qs.filter(roles__role=role_filter, roles__is_active=True).distinct()

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(display_name__icontains=search)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)

        serializer = PartyListSerializer(rows, many=True)
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": serializer.data},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        company = getattr(request, "company", None)
        if company is None:
            return Response({"detail": "Company context required."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = PartyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            party = create_party(
                company=company,
                request=request,
                actor=request.user,
                **serializer.validated_data,
            )
        except DjangoValidationError as exc:
            return Response({"detail": _validation_error_detail(exc)}, status=status.HTTP_400_BAD_REQUEST)

        out = PartyListSerializer(party).data
        return Response(out, status=status.HTTP_201_CREATED)


class PartyDetailView(APIView):
    """
    GET    /api/parties/<id>/   — Detalle de party.
    PATCH  /api/parties/<id>/   — Actualizar party.
    """

    permission_classes = [rbac_permission("parties.read")]
    throttle_scope = "heavy_reads"

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [rbac_permission("parties.write")()]
        return super().get_permissions()

    def _get_party(self, request, party_id):
        company = getattr(request, "company", None)
        if company is None:
            return None, Response({"detail": "Company context required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            party = Party.objects.prefetch_related("roles").get(pk=party_id, company=company)
        except Party.DoesNotExist:
            return None, Response({"detail": "Party not found."}, status=status.HTTP_404_NOT_FOUND)
        return party, None

    def get(self, request, party_id):
        party, err = self._get_party(request, party_id)
        if err:
            return err
        return Response(PartyListSerializer(party).data)

    def patch(self, request, party_id):
        party, err = self._get_party(request, party_id)
        if err:
            return err

        serializer = PartyUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        updates = {k: v for k, v in serializer.validated_data.items()}
        if not updates:
            return Response({"detail": "No fields to update."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            party = update_party(party=party, request=request, actor=request.user, **updates)
        except DjangoValidationError as exc:
            return Response({"detail": _validation_error_detail(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PartyListSerializer(party).data)


class PartyRoleView(APIView):
    """
    POST   /api/parties/<id>/roles/assign/   — Asignar rol.
    POST   /api/parties/<id>/roles/revoke/   — Revocar rol.
    GET    /api/parties/<id>/roles/          — Listar roles del party.
    """

    permission_classes = [rbac_permission("parties.roles.write")]
    throttle_scope = "heavy_reads"

    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("parties.read")()]
        return super().get_permissions()

    def _get_party(self, request, party_id):
        company = getattr(request, "company", None)
        if company is None:
            return None, Response({"detail": "Company context required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            party = Party.objects.get(pk=party_id, company=company)
        except Party.DoesNotExist:
            return None, Response({"detail": "Party not found."}, status=status.HTTP_404_NOT_FOUND)
        return party, None

    def get(self, request, party_id):
        party, err = self._get_party(request, party_id)
        if err:
            return err
        roles = PartyRole.objects.filter(party=party).order_by("-created_at")

        return Response(PartyRoleSerializer(roles, many=True).data)


class PartyRoleAssignView(APIView):
    permission_classes = [rbac_permission("parties.roles.write")]
    throttle_scope = "heavy_reads"

    def post(self, request, party_id):
        company = getattr(request, "company", None)
        if company is None:
            return Response({"detail": "Company context required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            party = Party.objects.get(pk=party_id, company=company)
        except Party.DoesNotExist:
            return Response({"detail": "Party not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = PartyRoleAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            role_obj = assign_party_role(
                party=party,
                role=serializer.validated_data["role"],
                valid_from=serializer.validated_data.get("valid_from"),
                request=request,
                actor=request.user,
            )
        except DjangoValidationError as exc:
            return Response({"detail": _validation_error_detail(exc)}, status=status.HTTP_400_BAD_REQUEST)


        return Response(PartyRoleSerializer(role_obj).data, status=status.HTTP_201_CREATED)


class PartyRoleRevokeView(APIView):
    permission_classes = [rbac_permission("parties.roles.write")]
    throttle_scope = "heavy_reads"

    def post(self, request, party_id):
        company = getattr(request, "company", None)
        if company is None:
            return Response({"detail": "Company context required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            party = Party.objects.get(pk=party_id, company=company)
        except Party.DoesNotExist:
            return Response({"detail": "Party not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = PartyRoleRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            role_obj = revoke_party_role(
                party=party,
                role=serializer.validated_data["role"],
                valid_to=serializer.validated_data.get("valid_to"),
                request=request,
                actor=request.user,
            )
        except DjangoValidationError as exc:
            return Response({"detail": _validation_error_detail(exc)}, status=status.HTTP_400_BAD_REQUEST)


        return Response(PartyRoleSerializer(role_obj).data)
