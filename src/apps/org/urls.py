from django.urls import path

from .views import BranchDetailView, BranchListCreateView, CompanyProfileView

urlpatterns = [
    path("branches/", BranchListCreateView.as_view()),
    path("branches/<int:branch_id>/", BranchDetailView.as_view()),
    path("company/profile/", CompanyProfileView.as_view()),
]
