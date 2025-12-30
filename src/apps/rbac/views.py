from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import rbac_permission


class InventoryReadDemoView(APIView):
    """
    Endpoint demo para validar 403 contractual con required_permission.
    Luego puedes mover este patrón a endpoints reales.
    """
    permission_classes = [rbac_permission("inventory.read")]

    def get(self, request):
        return Response({"ok": True, "required_permission": "inventory.read"})

# Create your views here.
