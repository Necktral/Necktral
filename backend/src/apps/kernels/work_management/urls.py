"""Work Management Kernel - URL Configuration"""
from django.urls import path

from . import views

app_name = "work_management"

urlpatterns = [
    # WorkShift
    path("shifts/", views.WorkShiftListCreateView.as_view(), name="shift-list-create"),
    path("shifts/<int:pk>/", views.WorkShiftDetailView.as_view(), name="shift-detail"),
    # Attendance
    path("attendance/check-in/", views.AttendanceCheckInView.as_view(), name="attendance-check-in"),
    path("attendance/<int:pk>/check-out/", views.AttendanceCheckOutView.as_view(), name="attendance-check-out"),
    path("attendance/manual/", views.AttendanceManualView.as_view(), name="attendance-manual"),
    path("attendance/", views.AttendanceListView.as_view(), name="attendance-list"),
    # MaintenanceLog
    path("maintenance/", views.MaintenanceLogListCreateView.as_view(), name="maintenance-list-create"),
    path("maintenance/<int:pk>/", views.MaintenanceLogDetailView.as_view(), name="maintenance-detail"),
    path("maintenance/<int:pk>/submit/", views.MaintenanceLogSubmitView.as_view(), name="maintenance-submit"),
]
