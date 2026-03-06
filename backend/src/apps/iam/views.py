from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


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
