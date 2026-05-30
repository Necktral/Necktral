from django.urls import path

from .views import (
    ACLSnapshotView,
    AdminGrantListView,
    CompanyLinkListView,
    ContextEchoView,
    MembershipListView,
    MyBranchesView,
    MyCompaniesView,
    OrgUnitListView,
)

urlpatterns = [
    path("context/", ContextEchoView.as_view(), name="iam-context"),
    path("acl/", ACLSnapshotView.as_view(), name="iam-acl-snapshot"),
    path("org-units/", OrgUnitListView.as_view(), name="iam-orgunit-list"),
    path("my-companies/", MyCompaniesView.as_view(), name="iam-my-companies"),
    path("my-branches/", MyBranchesView.as_view(), name="iam-my-branches"),
    path("memberships/", MembershipListView.as_view(), name="iam-memberships"),
    path("admin-grants/", AdminGrantListView.as_view(), name="iam-admin-grants"),
    path("company-links/", CompanyLinkListView.as_view(), name="iam-company-links"),
]
