from __future__ import annotations


class ScopedQuerysetMixin:
    """Mixin para forzar scope por company/branch en querysets.

    Requiere:
    - company_field: nombre del campo FK a company en el modelo.
    - branch_field: nombre del campo FK a branch en el modelo (opcional).
    """

    company_field = "company"
    branch_field = "branch"

    def get_queryset(self):
        qs = super().get_queryset()
        request = getattr(self, "request", None)
        if request is None:
            return qs

        company = getattr(request, "company", None)
        branch = getattr(request, "branch", None)

        if company is not None:
            qs = qs.filter(**{self.company_field: company})
        if branch is not None and self.branch_field:
            qs = qs.filter(**{self.branch_field: branch})
        return qs
