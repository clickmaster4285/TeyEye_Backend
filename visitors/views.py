from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import (
    Visitor,
    ZoneAccessLog,
    SecurityAlert,
    Vehicle,
    VisitorNotification,
    VmsListRecord,
)
from .serializers import (
    VisitorSerializer,
    VisitorWriteSerializer,
    FaceCaptureSerializer,
    ZoneScanSerializer,
    SecurityAlertSerializer,
    ApproveDenySerializer,
    NotifyHostSerializer,
    VehicleSerializer,
    VisitorNotificationSerializer,
    VmsListRecordSerializer,
    VmsListBulkSerializer,
)
from users.permissions import apply_location_filter, get_effective_location, resolve_location_for_write
from .payload_utils import merge_extra_into_response


def get_visitor_queryset():
    return Visitor.objects.all().order_by("-created_at")


def filter_visitors_by_request(queryset, request):
    queryset = apply_location_filter(
        queryset,
        request.user,
        field="location",
        query_param=request.query_params.get("location"),
    )
    source = request.query_params.get("registration_source", "").strip()
    if source:
        queryset = queryset.filter(registration_source=source)
    status_param = request.query_params.get("registration_status", "").strip()
    if status_param:
        queryset = queryset.filter(registration_status=status_param)
    approval = request.query_params.get("approval_status", "").strip()
    if approval:
        queryset = queryset.filter(approval_status=approval)
    search = request.query_params.get("search", "").strip()
    if search:
        queryset = queryset.filter(
            Q(full_name__icontains=search)
            | Q(cnic_number__icontains=search)
            | Q(passport_number__icontains=search)
            | Q(qr_code_id__icontains=search)
        )
    return queryset


def serialize_visitor_list(queryset):
    from .serializers import VisitorListSerializer

    ser = VisitorListSerializer(queryset, many=True, context={"omit_blobs": True})
    return ser.data


# ---------- Visitor CRUD ----------


class VisitorListAPIView(generics.ListAPIView):
    """GET /api/visitors/list/?registration_source=walk-in|pre-registration"""

    serializer_class = VisitorSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return filter_visitors_by_request(get_visitor_queryset(), self.request)

    def get_serializer_class(self):
        from .serializers import VisitorListSerializer

        return VisitorListSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["omit_blobs"] = True
        return context


class VisitorCreateAPIView(APIView):
    """POST /api/visitors/create/ — body may include registration_source query or field."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        source = (
            request.data.get("registration_source")
            or request.query_params.get("registration_source")
            or ""
        )
        write_ser = VisitorWriteSerializer(
            data=request.data,
            context={"registration_source": str(source), "request": request},
        )
        if not write_ser.is_valid():
            return Response(write_ser.errors, status=status.HTTP_400_BAD_REQUEST)
        visitor = write_ser.save()
        return Response(VisitorSerializer(visitor).data, status=status.HTTP_201_CREATED)


class VisitorReadAPIView(generics.RetrieveAPIView):
    serializer_class = VisitorSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return filter_visitors_by_request(get_visitor_queryset(), self.request)


class VisitorProfileImageAPIView(APIView):
    """GET /api/visitors/<pk>/profile-image/ — visitor photo for list avatars (blobs omitted from list JSON)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        from django.http import HttpResponse

        from .payload_utils import get_visitor_profile_photo_bytes

        qs = filter_visitors_by_request(get_visitor_queryset(), request)
        try:
            visitor = qs.get(pk=pk)
        except Visitor.DoesNotExist:
            return Response({"detail": "Visitor not found."}, status=status.HTTP_404_NOT_FOUND)

        parsed = get_visitor_profile_photo_bytes(visitor)
        if not parsed:
            return Response({"detail": "No photo for this visitor."}, status=status.HTTP_404_NOT_FOUND)

        content_type, body = parsed
        response = HttpResponse(body, content_type=content_type)
        response["Cache-Control"] = "private, max-age=3600"
        return response


class VisitorUpdateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        return self._update(request, pk, partial=False)

    def patch(self, request, pk):
        return self._update(request, pk, partial=True)

    def _update(self, request, pk, partial):
        qs = filter_visitors_by_request(get_visitor_queryset(), request)
        try:
            visitor = qs.get(pk=pk)
        except Visitor.DoesNotExist:
            return Response({"detail": "Visitor not found."}, status=status.HTTP_404_NOT_FOUND)
        write_ser = VisitorWriteSerializer(
            visitor,
            data=request.data,
            partial=partial,
            context={"request": request},
        )
        if not write_ser.is_valid():
            return Response(write_ser.errors, status=status.HTTP_400_BAD_REQUEST)
        visitor = write_ser.save()
        return Response(VisitorSerializer(visitor).data)


class VisitorDeleteAPIView(generics.DestroyAPIView):
    queryset = Visitor.objects.all()
    serializer_class = VisitorSerializer
    permission_classes = [permissions.IsAuthenticated]


class VisitorCnicCheckAPIView(APIView):
    """GET /api/visitors/check-cnic/?cnic=..."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cnic = str(request.query_params.get("cnic", "")).strip().replace(" ", "").replace("-", "")
        if not cnic:
            return Response({"exists": False})
        digits = "".join(c for c in cnic if c.isdigit())
        exists = Visitor.objects.filter(
            Q(cnic_number__icontains=digits) | Q(cnic_passport__icontains=digits)
        ).exists()
        return Response({"exists": exists})


# ---------- Active & Approval ----------


class ActiveVisitorsAPIView(APIView):
    """GET /api/visitors/active/"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Visitor.objects.filter(
            flow_stage="zone_checked_in",
            expiry_status="active",
        ).order_by("-updated_at")
        qs = filter_visitors_by_request(qs, request)
        return Response(serialize_visitor_list(qs))


class PendingApprovalsAPIView(APIView):
    """GET /api/approval/pending/"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Visitor.objects.filter(approval_status="pending").order_by("-created_at")
        qs = filter_visitors_by_request(qs, request)
        return Response(serialize_visitor_list(qs))


class VisitorApproveAPIView(APIView):
    """POST /api/visitors/<id>/approve/"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            visitor = Visitor.objects.get(pk=pk)
        except Visitor.DoesNotExist:
            return Response({"detail": "Visitor not found."}, status=status.HTTP_404_NOT_FOUND)
        ser = ApproveDenySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        visitor.approval_status = "approved"
        visitor.approved_by = ser.validated_data.get("approved_by") or "system"
        visitor.registration_status = "approved"
        if visitor.flow_stage == "arrived":
            visitor.flow_stage = "registered"
        visitor.save()
        return Response(VisitorSerializer(visitor).data)


class VisitorDenyAPIView(APIView):
    """POST /api/visitors/<id>/deny/"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            visitor = Visitor.objects.get(pk=pk)
        except Visitor.DoesNotExist:
            return Response({"detail": "Visitor not found."}, status=status.HTTP_404_NOT_FOUND)
        ser = ApproveDenySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        visitor.approval_status = "denied"
        visitor.denied_by = ser.validated_data.get("denied_by") or "system"
        visitor.rejection_reason = ser.validated_data.get("rejection_reason") or ""
        visitor.expiry_status = "revoked"
        visitor.save()
        return Response(VisitorSerializer(visitor).data)


class VisitorNotifyHostAPIView(APIView):
    """POST /api/visitors/<id>/notify-host/"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            visitor = Visitor.objects.get(pk=pk)
        except Visitor.DoesNotExist:
            return Response({"detail": "Visitor not found."}, status=status.HTTP_404_NOT_FOUND)
        ser = NotifyHostSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        recipient = ser.validated_data.get("recipient") or visitor.host_email or visitor.host_contact_number
        if not recipient:
            return Response(
                {"detail": "No host email or phone on file."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        now = timezone.now()
        VisitorNotification.objects.create(
            visitor=visitor,
            notification_type="host_notify",
            recipient=recipient,
            message=f"Visitor {visitor.full_name} is scheduled / on site.",
            success=True,
        )
        visitor.host_notified_at = now
        visitor.save(update_fields=["host_notified_at", "updated_at"])
        return Response(
            {"host_notified_at": now.isoformat(), "recipient": recipient},
            status=status.HTTP_200_OK,
        )


# ---------- Face Capture ----------


class VisitorFaceCaptureAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            visitor = Visitor.objects.get(pk=pk)
        except Visitor.DoesNotExist:
            return Response({"detail": "Visitor not found."}, status=status.HTTP_404_NOT_FOUND)
        ser = FaceCaptureSerializer(data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        for key, value in ser.validated_data.items():
            setattr(visitor, key, value or "")
        visitor.flow_stage = "face_captured"
        visitor.save(update_fields=list(ser.validated_data.keys()) + ["flow_stage", "updated_at"])
        return Response(VisitorSerializer(visitor).data)


# ---------- Zone Scan ----------


class ZoneScanAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ser = ZoneScanSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        qr_code_id = ser.validated_data["qr_code_id"].strip()
        zone = ser.validated_data["zone"].strip()
        gate = ser.validated_data.get("gate") or ""
        scan_type = ser.validated_data.get("scan_type") or "entry"
        scanner_id = ser.validated_data.get("scanner_id") or ""

        try:
            visitor = Visitor.objects.get(qr_code_id=qr_code_id)
        except Visitor.DoesNotExist:
            SecurityAlert.objects.create(
                visitor=None,
                alert_type="invalid_qr",
                severity="high",
                message=f"Scan with unknown QR code: {qr_code_id} at zone={zone} gate={gate}",
                zone=zone,
                gate=gate,
            )
            return Response(
                {
                    "allowed": False,
                    "message": "Invalid or unknown QR code.",
                    "alert_created": True,
                },
                status=status.HTTP_200_OK,
            )

        allowed = True
        msg = "Access granted."

        from .screening_utils import apply_visitor_screening, visitor_blocks_entry

        apply_visitor_screening(visitor, create_alert=False)
        blocked, block_msg = visitor_blocks_entry(visitor)
        if blocked:
            allowed = False
            msg = block_msg
            SecurityAlert.objects.create(
                visitor=visitor,
                alert_type="watchlist_hit",
                severity="critical",
                message=msg,
                zone=zone,
                gate=gate,
            )

        if allowed and visitor.approval_status == "denied":
            allowed = False
            msg = "Visitor approval was denied."
            SecurityAlert.objects.create(
                visitor=visitor,
                alert_type="other",
                severity="high",
                message=msg,
                zone=zone,
                gate=gate,
            )

        if allowed and visitor.expiry_status in ("expired", "revoked"):
            allowed = False
            msg = f"QR code is {visitor.expiry_status}."
            SecurityAlert.objects.create(
                visitor=visitor,
                alert_type="expired_qr",
                severity="high",
                message=msg,
                zone=zone,
                gate=gate,
            )

        if allowed and visitor.access_zone and visitor.access_zone != "all":
            if zone != visitor.access_zone:
                allowed = False
                msg = f"Visitor not allowed in zone: {zone}."
                SecurityAlert.objects.create(
                    visitor=visitor,
                    alert_type="mismatch_zone",
                    severity="medium",
                    message=msg,
                    zone=zone,
                    gate=gate,
                )

        if allowed and scan_type == "entry":
            recent_entry = ZoneAccessLog.objects.filter(
                visitor=visitor,
                scan_type="entry",
                allowed=True,
                scanned_at__gte=timezone.now() - timedelta(minutes=5),
            ).exists()
            if recent_entry and visitor.flow_stage == "zone_checked_in":
                allowed = False
                msg = "Duplicate entry scan detected."
                SecurityAlert.objects.create(
                    visitor=visitor,
                    alert_type="duplicate_entry",
                    severity="medium",
                    message=msg,
                    zone=zone,
                    gate=gate,
                )

        ZoneAccessLog.objects.create(
            visitor=visitor,
            zone=zone,
            gate=gate,
            scan_type=scan_type,
            allowed=allowed,
            message=msg,
            scanner_id=scanner_id,
        )

        if allowed:
            visitor.scan_count = (visitor.scan_count or 0) + 1
            if visitor.flow_stage in ("registered", "face_captured", "qr_printed"):
                visitor.flow_stage = "zone_checked_in"
            elif scan_type == "exit":
                visitor.flow_stage = "exited"
            visitor.save(update_fields=["scan_count", "flow_stage", "updated_at"])

        return Response(
            {
                "allowed": allowed,
                "message": msg,
                "visitor_id": visitor.id,
                "visitor_name": visitor.full_name,
                "flow_stage": visitor.flow_stage,
            },
            status=status.HTTP_200_OK,
        )


# ---------- Security ----------


class SecurityAlertListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SecurityAlertSerializer

    def get_queryset(self):
        qs = SecurityAlert.objects.all().select_related("visitor")
        acknowledged = self.request.query_params.get("acknowledged")
        if acknowledged is not None:
            if acknowledged.lower() in ("false", "0", "no"):
                qs = qs.filter(acknowledged=False)
            elif acknowledged.lower() in ("true", "1", "yes"):
                qs = qs.filter(acknowledged=True)
        severity = self.request.query_params.get("severity")
        if severity:
            qs = qs.filter(severity=severity)
        return qs[:100]


class SecurityAlertAcknowledgeAPIView(APIView):
    """POST /api/security/alerts/<id>/acknowledge/"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            alert = SecurityAlert.objects.get(pk=pk)
        except SecurityAlert.DoesNotExist:
            return Response({"detail": "Alert not found."}, status=status.HTTP_404_NOT_FOUND)
        alert.acknowledged = True
        alert.acknowledged_at = timezone.now()
        alert.acknowledged_by = request.data.get("acknowledged_by") or "operator"
        alert.save()
        return Response(SecurityAlertSerializer(alert).data)


class SecurityDashboardAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()
        visitors_today = Visitor.objects.filter(created_at__date=today).count()
        in_building = Visitor.objects.filter(flow_stage="zone_checked_in").count()
        alerts_unack = SecurityAlert.objects.filter(acknowledged=False).count()
        alerts_today = SecurityAlert.objects.filter(created_at__date=today).count()
        recent_alerts = SecurityAlert.objects.filter(acknowledged=False)[:10]
        return Response(
            {
                "visitors_today": visitors_today,
                "in_building": in_building,
                "alerts_unacknowledged": alerts_unack,
                "alerts_today": alerts_today,
                "recent_alerts": SecurityAlertSerializer(recent_alerts, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


# ---------- Vehicles ----------


class VehicleListAPIView(generics.ListAPIView):
    serializer_class = VehicleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Vehicle.objects.select_related("visitor").all()
        visitor_id = self.request.query_params.get("visitor_id")
        if visitor_id:
            qs = qs.filter(visitor_id=visitor_id)
        return qs


class VehicleCreateAPIView(generics.CreateAPIView):
    serializer_class = VehicleSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Vehicle.objects.all()


# ---------- Notifications ----------


class NotificationListAPIView(generics.ListAPIView):
    serializer_class = VisitorNotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = VisitorNotification.objects.select_related("visitor").all()
        visitor_id = self.request.query_params.get("visitor_id")
        if visitor_id:
            qs = qs.filter(visitor_id=visitor_id)
        return qs


# ---------- VMS Analytics ----------


class VmsAnalyticsAPIView(APIView):
    """GET /api/vms/analytics/?from=YYYY-MM-DD&to=YYYY-MM-DD"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()
        from_str = request.query_params.get("from") or str(today)
        to_str = request.query_params.get("to") or str(today)
        try:
            from_date = date.fromisoformat(from_str[:10])
            to_date = date.fromisoformat(to_str[:10])
        except ValueError:
            from_date = today
            to_date = today

        visitors_registered = Visitor.objects.filter(
            created_at__date__gte=from_date,
            created_at__date__lte=to_date,
        ).count()
        in_building_now = Visitor.objects.filter(flow_stage="zone_checked_in").count()
        zone_scans = ZoneAccessLog.objects.filter(
            scanned_at__date__gte=from_date,
            scanned_at__date__lte=to_date,
        ).count()
        alerts_in_range = SecurityAlert.objects.filter(
            created_at__date__gte=from_date,
            created_at__date__lte=to_date,
        ).count()
        alerts_unacknowledged = SecurityAlert.objects.filter(acknowledged=False).count()
        pending_approvals = Visitor.objects.filter(approval_status="pending").count()
        approved_in_range = Visitor.objects.filter(
            approval_status="approved",
            updated_at__date__gte=from_date,
            updated_at__date__lte=to_date,
        ).count()
        denied_in_range = Visitor.objects.filter(
            approval_status="denied",
            updated_at__date__gte=from_date,
            updated_at__date__lte=to_date,
        ).count()

        return Response(
            {
                "from_date": str(from_date),
                "to_date": str(to_date),
                "visitors_registered": visitors_registered,
                "in_building_now": in_building_now,
                "zone_scans_in_range": zone_scans,
                "alerts_in_range": alerts_in_range,
                "alerts_unacknowledged": alerts_unacknowledged,
                "pending_approvals": pending_approvals,
                "approved_in_range": approved_in_range,
                "denied_in_range": denied_in_range,
            }
        )


def _visitor_clearance_label(visitor):
    status = (visitor.watchlist_check_status or "").lower()
    if "blacklist" in status or "flagged" in status:
        return "Blacklisted"
    if visitor.approval_status == "denied":
        return "Rejected"
    if visitor.approval_status == "pending":
        return "Pending Approval"
    if visitor.registration_status == "draft":
        return "Pending Docs"
    return "Cleared"


def _visitor_priority_label(visitor):
    view = (visitor.preferred_view_visit or "").lower()
    if view == "high-security":
        return "High"
    if view == "logins":
        return "Urgent"
    return "Normal"


def _visitor_datetime_label(visitor):
    date_part = ""
    if visitor.preferred_visit_date:
        date_part = visitor.preferred_visit_date.strftime("%d-%m-%Y")
    elif visitor.visit_date:
        date_part = visitor.visit_date.strftime("%d-%m-%Y")
    elif visitor.created_at:
        date_part = visitor.created_at.strftime("%d-%m-%Y")
    slot = visitor.preferred_time_slot or visitor.preferred_time_slot_walkin or ""
    if slot:
        return f"{date_part} | {slot}" if date_part else slot
    return date_part or "—"


def _serialize_overview_visitor(visitor):
    vehicles = list(visitor.vehicles.all()[:1])
    plate = vehicles[0].plate_number if vehicles else "-"
    clearance = _visitor_clearance_label(visitor)
    approval = visitor.approval_status or "pending"
    return {
        "id": visitor.id,
        "reg_id": str(visitor.id),
        "date": visitor.created_at.strftime("%d-%m-%Y") if visitor.created_at else "—",
        "visitor_name": visitor.full_name,
        "organization": visitor.organization_name or "—",
        "vehicle_id": plate,
        "status": clearance,
        "host_name": visitor.host_full_name or visitor.host_officer_name or "—",
        "date_time": _visitor_datetime_label(visitor),
        "priority": _visitor_priority_label(visitor),
        "approval_status": approval,
        "registration_source": visitor.registration_source or "",
    }


class VmsOverviewAPIView(APIView):
    """GET /api/vms/overview/ — dashboard stats and recent visitor rows."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()
        qs = filter_visitors_by_request(get_visitor_queryset(), request)

        expected_today = qs.filter(
            Q(preferred_visit_date=today) | Q(visit_date=today)
        ).count()
        checked_in = qs.filter(
            flow_stage="zone_checked_in", expiry_status="active"
        ).count()
        pending_docs = qs.filter(registration_status="draft").count()
        pending_approval = qs.filter(approval_status="pending").count()
        rejected_requests = qs.filter(approval_status="denied").count()
        active_passes = qs.filter(
            approval_status="approved",
            expiry_status="active",
        ).exclude(flow_stage="exited").count()

        location = get_effective_location(
            request.user, request.query_params.get("location")
        )
        bl_qs = VmsListRecord.objects.filter(module="vms_blacklist_management_rows")
        if location:
            bl_qs = bl_qs.filter(location=location)
        blacklisted_visitors = bl_qs.count()
        if blacklisted_visitors == 0:
            blacklisted_visitors = qs.filter(
                watchlist_check_status__icontains="blacklist"
            ).count()

        blacklisted_vehicles = 0
        vehicle_rows = VmsListRecord.objects.filter(module="vms_vehicle_entries")
        if location:
            vehicle_rows = vehicle_rows.filter(location=location)
        for record in vehicle_rows:
            data = record.data or {}
            status = str(data.get("status") or data.get("vehicle_status") or "").lower()
            if "blacklist" in status:
                blacklisted_vehicles += 1

        recent_qs = qs.prefetch_related("vehicles")[:10]
        registered_qs = (
            qs.filter(approval_status="approved")
            .prefetch_related("vehicles")
            .order_by("-created_at")[:10]
        )

        return Response(
            {
                "expected_today": expected_today,
                "checked_in": checked_in,
                "pending_docs": pending_docs,
                "pending_approval": pending_approval,
                "blacklisted_visitors": blacklisted_visitors,
                "blacklisted_vehicles": blacklisted_vehicles,
                "rejected_requests": rejected_requests,
                "active_passes": active_passes,
                "visitors_registered_today": qs.filter(created_at__date=today).count(),
                "recent_registrations": [
                    _serialize_overview_visitor(v) for v in recent_qs
                ],
                "registered_visitors": [
                    _serialize_overview_visitor(v) for v in registered_qs
                ],
            }
        )


# ---------- VMS List storage (blacklist, watchlist, etc.) ----------


class VmsListRecordsAPIView(APIView):
    """
    GET /api/vms/lists/?module=vms_blacklist_management_rows
    PUT /api/vms/lists/  body: { module, rows: [{ id, ...fields }] }
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        module = request.query_params.get("module", "").strip()
        if not module:
            return Response({"detail": "module query param required."}, status=400)
        records = VmsListRecord.objects.filter(module=module)
        location = get_effective_location(
            request.user, request.query_params.get("location")
        )
        if location:
            records = records.filter(location=location)
        rows = [{"id": r.record_id, **(r.data or {})} for r in records]
        return Response(rows)

    def put(self, request):
        ser = VmsListBulkSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        module = ser.validated_data["module"]
        rows = ser.validated_data["rows"]
        location = resolve_location_for_write(
            request.user, ser.validated_data.get("location") or ""
        )
        if location:
            VmsListRecord.objects.filter(module=module, location=location).delete()
        else:
            VmsListRecord.objects.filter(module=module).delete()
        bulk = []
        for row in rows:
            record_id = str(row.get("id") or f"row-{timezone.now().timestamp()}")
            data = {k: v for k, v in row.items() if k != "id"}
            bulk.append(
                VmsListRecord(
                    module=module,
                    record_id=record_id,
                    data=data,
                    location=location or str(row.get("location") or ""),
                )
            )
        if bulk:
            VmsListRecord.objects.bulk_create(bulk)
        if module in ("vms_watchlist_screening_rows", "vms_blacklist_management_rows"):
            from .screening_utils import rescreen_all_visitors

            rescreen_all_visitors(location=location or "")
        return Response({"module": module, "count": len(bulk)})


class VmsScreeningSummaryAPIView(APIView):
    """GET /api/vms/screening/summary/ — visitor screening status counts."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = filter_visitors_by_request(get_visitor_queryset(), request)
        return Response(
            {
                "total": qs.count(),
                "cleared": qs.filter(watchlist_check_status="cleared").count(),
                "flagged": qs.filter(watchlist_check_status="flagged").count(),
                "potential": qs.filter(watchlist_check_status="potential").count(),
                "blacklisted": qs.filter(
                    watchlist_check_status__icontains="blacklist"
                ).count(),
                "not_checked": qs.filter(
                    Q(watchlist_check_status="") | Q(watchlist_check_status__isnull=True)
                ).count(),
            }
        )


class VmsScreeningRescreenAPIView(APIView):
    """POST /api/vms/screening/rescreen/ — re-run screening for one or all visitors."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .screening_utils import apply_visitor_screening, rescreen_all_visitors

        visitor_id = request.data.get("visitor_id")
        if visitor_id:
            try:
                visitor = Visitor.objects.get(pk=visitor_id)
            except Visitor.DoesNotExist:
                return Response({"detail": "Visitor not found."}, status=404)
            apply_visitor_screening(visitor)
            return Response({"screened": 1})

        location = get_effective_location(
            request.user, request.data.get("location")
        )
        count = rescreen_all_visitors(location=location or "")
        return Response({"screened": count})


class VmsScreeningMarkAPIView(APIView):
    """POST /api/vms/screening/mark/ — flag or blacklist a registered visitor."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .screening_utils import mark_visitor_blacklisted, mark_visitor_flagged

        visitor_id = request.data.get("visitor_id")
        action = str(request.data.get("action") or "").strip().lower()
        remarks = str(request.data.get("remarks") or "").strip()
        marked_by = str(request.data.get("marked_by") or request.user.username or "security").strip()

        if not visitor_id:
            return Response({"detail": "visitor_id is required."}, status=400)
        if action not in ("flagged", "blacklisted"):
            return Response(
                {"detail": "action must be 'flagged' or 'blacklisted'."},
                status=400,
            )

        try:
            visitor = Visitor.objects.get(pk=visitor_id)
        except Visitor.DoesNotExist:
            return Response({"detail": "Visitor not found."}, status=404)

        if action == "flagged":
            result = mark_visitor_flagged(visitor, remarks=remarks, marked_by=marked_by)
        else:
            result = mark_visitor_blacklisted(visitor, reason=remarks, marked_by=marked_by)

        return Response(
            {
                "visitor_id": visitor.pk,
                "watchlist_check_status": visitor.watchlist_check_status,
                "screening": result.as_extra(),
            }
        )
