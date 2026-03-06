from __future__ import annotations



class MethodThrottleScopeMixin:
    """Permite elegir throttle_scope por metodo HTTP.

    Uso:
        class Foo(MethodThrottleScopeMixin, APIView):
            throttle_scope_by_method = {"GET": "heavy_reads", "POST": "admin_writes"}
    """

    throttle_scope_by_method: dict[str, str] = {}
    default_throttle_scope: str | None = None

    def get_throttles(self):
        scope = self.throttle_scope_by_method.get(self.request.method)
        if scope:
            self.throttle_scope = scope
        elif self.default_throttle_scope:
            self.throttle_scope = self.default_throttle_scope
        return super().get_throttles()
