from django.urls import path
from .views import (
    VisitorListAPIView,
    VisitorCreateAPIView,
    VisitorReadAPIView,
    VisitorProfileImageAPIView,
    VisitorUpdateAPIView,
    VisitorDeleteAPIView,
    VisitorCnicCheckAPIView,
    VisitorFaceCaptureAPIView,
    ActiveVisitorsAPIView,
    PendingApprovalsAPIView,
    VisitorApproveAPIView,
    VisitorDenyAPIView,
    VisitorNotifyHostAPIView,
    ZoneScanAPIView,
    SecurityAlertListAPIView,
    SecurityAlertAcknowledgeAPIView,
    SecurityDashboardAPIView,
    VehicleListAPIView,
    VehicleCreateAPIView,
    NotificationListAPIView,
    VmsAnalyticsAPIView,
    VmsOverviewAPIView,
    VmsListRecordsAPIView,
    VmsScreeningSummaryAPIView,
    VmsScreeningRescreenAPIView,
    VmsScreeningMarkAPIView,
)

urlpatterns = [
    # Visitor CRUD
    path("visitors/list/", VisitorListAPIView.as_view(), name="visitor-list"),
    path("visitors/create/", VisitorCreateAPIView.as_view(), name="visitor-create"),
    path("visitors/check-cnic/", VisitorCnicCheckAPIView.as_view(), name="visitor-check-cnic"),
    path("visitors/active/", ActiveVisitorsAPIView.as_view(), name="visitor-active"),
    path("visitors/<int:pk>/read/", VisitorReadAPIView.as_view(), name="visitor-read"),
    path(
        "visitors/<int:pk>/profile-image/",
        VisitorProfileImageAPIView.as_view(),
        name="visitor-profile-image",
    ),
    path("visitors/<int:pk>/update/", VisitorUpdateAPIView.as_view(), name="visitor-update"),
    path("visitors/<int:pk>/delete/", VisitorDeleteAPIView.as_view(), name="visitor-delete"),
    path("visitors/<int:pk>/face-capture/", VisitorFaceCaptureAPIView.as_view(), name="visitor-face-capture"),
    path("visitors/<int:pk>/approve/", VisitorApproveAPIView.as_view(), name="visitor-approve"),
    path("visitors/<int:pk>/deny/", VisitorDenyAPIView.as_view(), name="visitor-deny"),
    path("visitors/<int:pk>/notify-host/", VisitorNotifyHostAPIView.as_view(), name="visitor-notify-host"),
    # Approval
    path("approval/pending/", PendingApprovalsAPIView.as_view(), name="approval-pending"),
    # Zone access
    path("zone-access/scan/", ZoneScanAPIView.as_view(), name="zone-scan"),
    # Security
    path("security/alerts/", SecurityAlertListAPIView.as_view(), name="security-alerts"),
    path("security/alerts/<int:pk>/acknowledge/", SecurityAlertAcknowledgeAPIView.as_view(), name="security-alert-ack"),
    path("security/dashboard/", SecurityDashboardAPIView.as_view(), name="security-dashboard"),
    # Vehicles
    path("vehicles/", VehicleListAPIView.as_view(), name="vehicle-list"),
    path("vehicles/create/", VehicleCreateAPIView.as_view(), name="vehicle-create"),
    # Notifications
    path("notifications/", NotificationListAPIView.as_view(), name="notification-list"),
    # Analytics & list storage
    path("vms/analytics/", VmsAnalyticsAPIView.as_view(), name="vms-analytics"),
    path("vms/overview/", VmsOverviewAPIView.as_view(), name="vms-overview"),
    path("vms/lists/", VmsListRecordsAPIView.as_view(), name="vms-lists"),
    path("vms/screening/summary/", VmsScreeningSummaryAPIView.as_view(), name="vms-screening-summary"),
    path("vms/screening/rescreen/", VmsScreeningRescreenAPIView.as_view(), name="vms-screening-rescreen"),
    path("vms/screening/mark/", VmsScreeningMarkAPIView.as_view(), name="vms-screening-mark"),
]
