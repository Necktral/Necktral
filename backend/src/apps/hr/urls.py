from django.urls import path

from .views import (
    EmployeeAssignmentListCreateView,
    EmployeeAssignmentEndView,
    EmployeeDetailView,
    EmployeeListCreateView,
    EmployeeProvisionUserView,
    EmployeeRevokeAccessView,
    EmployeeResetTempPasswordView,
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
    path("employees/<int:employee_id>/assignments/", EmployeeAssignmentListCreateView.as_view()),
    path("employees/<int:employee_id>/assignments/<int:assignment_id>/end/", EmployeeAssignmentEndView.as_view()),
    path("employees/<int:employee_id>/provision-user/", EmployeeProvisionUserView.as_view()),
    path("employees/<int:employee_id>/reset-temp-password/", EmployeeResetTempPasswordView.as_view()),
    path("employees/<int:employee_id>/revoke-access/", EmployeeRevokeAccessView.as_view()),
]
