from django.urls import path

from .views import (
    BootstrapOrganizationView,
    CompanyListCreateView,
    CompanyProfileView,
    BranchDetailView,
    BranchListCreateView,
)

urlpatterns = [
    path("bootstrap/organization/", BootstrapOrganizationView.as_view(), name="org-bootstrap-organization"),
    path("company/profile/", CompanyProfileView.as_view(), name="org-company-profile"),
    path("companies/", CompanyListCreateView.as_view(), name="org-companies"),
    path("branches/", BranchListCreateView.as_view(), name="org-branches"),
    path("branches/<int:branch_id>/", BranchDetailView.as_view(), name="org-branch-detail"),
]
