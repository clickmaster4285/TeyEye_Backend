from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    StaffViewSet,
    AttendanceViewSet,
    LoginView,
    UserViewSet,
    LeaveTypeViewSet,
    LeaveRequestViewSet,
    PayrollRunViewSet,
)

router = DefaultRouter()
router.register(r"staff", StaffViewSet, basename="staff")
router.register(r"attendance", AttendanceViewSet, basename="attendance")
router.register(r"users", UserViewSet, basename="users")
router.register(r"leave-types", LeaveTypeViewSet, basename="leave-type")
router.register(r"leave-requests", LeaveRequestViewSet, basename="leave-request")
router.register(r"payroll-runs", PayrollRunViewSet, basename="payroll-run")

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/login", LoginView.as_view(), name="login-no-slash"), 
    path("", include(router.urls)),
]