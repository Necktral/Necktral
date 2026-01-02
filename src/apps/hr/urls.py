from django.urls import path

from .views import (
    EmployeeAssignmentCreateView,
    EmployeeAssignmentEndView,
    EmployeeDetailView,
    EmployeeListCreateView,
    PositionDetailView,
    PositionListCreateView,
    PositionRoleMapUpdateView,
)

urlpatterns = [
    path("positions/", PositionListCreateView.as_view()),
    path("positions/<int:position_id>/", PositionDetailView.as_view()),
    path("positions/<int:position_id>/roles/", PositionRoleMapUpdateView.as_view()),
    path("employees/", EmployeeListCreateView.as_view()),
    path("employees/<int:employee_id>/", EmployeeDetailView.as_view()),
    path("employees/<int:employee_id>/assignments/", EmployeeAssignmentCreateView.as_view()),
    path("employees/<int:employee_id>/assignments/<int:assignment_id>/end/", EmployeeAssignmentEndView.as_view()),
]
