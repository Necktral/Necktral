import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger("apps.security.csp")


@csrf_exempt
def csp_report(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    payload = {}
    try:
        body = request.body.decode("utf-8") if request.body else ""
        payload = json.loads(body) if body else {}
    except Exception:
        payload = {"raw": (request.body or b"")[:2048].decode("utf-8", errors="replace")}

    logger.warning("CSP report received", extra={"csp_report": payload})
    return HttpResponse(status=204)
