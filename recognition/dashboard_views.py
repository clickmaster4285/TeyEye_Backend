from datetime import datetime

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from recognition.models import FaceEnrollment
from users.models import Attendance, Staff
from users.permissions import IsAdminOrHR
from users.serializers import AttendanceSerializer


class DashboardSummaryView(APIView):
    permission_classes = [IsAdminOrHR]

    def get(self, request):
        today = timezone.localdate()
        total_staff = Staff.objects.count()
        trained_faces = FaceEnrollment.objects.filter(is_trained=True).count()
        today_records = Attendance.objects.filter(date=today).select_related("staff", "user")

        present = today_records.filter(
            Q(status=Attendance.STATUS_PRESENT) | Q(status=Attendance.STATUS_LATE) | Q(check_in__isnull=False)
        ).distinct().count()
        late = today_records.filter(status=Attendance.STATUS_LATE).count()
        checked_out = today_records.filter(check_out__isnull=False).count()
        # Count unique staff present; fall back to records with check_in
        present_staff_ids = set(
            today_records.exclude(staff_id=None).values_list("staff_id", flat=True)
        )
        absent = max(total_staff - len(present_staff_ids), 0)

        department_stats = (
            today_records.filter(staff__isnull=False)
            .values("staff__department")
            .annotate(
                total=Count("id"),
                present_count=Count("id", filter=Q(status=Attendance.STATUS_PRESENT)),
                late_count=Count("id", filter=Q(status=Attendance.STATUS_LATE)),
            )
            .order_by("staff__department")
        )

        recent = Attendance.objects.select_related("staff", "user").order_by(
            "-check_in", "-id"
        )[:10]

        return Response({
            "date": str(today),
            "summary": {
                "total_employees": total_staff,
                "trained_faces": trained_faces,
                "present_today": present,
                "late_today": late,
                "absent_today": absent,
                "checked_out_today": checked_out,
            },
            "department_stats": [
                {
                    "department": row["staff__department"] or "Unassigned",
                    "total": row["total"],
                    "present_count": row["present_count"],
                    "late_count": row["late_count"],
                }
                for row in department_stats
            ],
            "recent_activity": AttendanceSerializer(recent, many=True).data,
        })


class DailyReportView(APIView):
    permission_classes = [IsAdminOrHR]

    def get(self, request):
        date_str = request.query_params.get("date")
        if date_str:
            report_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            report_date = timezone.localdate()

        records = Attendance.objects.filter(date=report_date).select_related("staff", "user")
        present_staff_ids = set(records.exclude(staff_id=None).values_list("staff_id", flat=True))
        # Also include user-linked staff
        for user_id in records.exclude(user_id=None).values_list("user_id", flat=True):
            staff = Staff.objects.filter(user_id=user_id).first()
            if staff:
                present_staff_ids.add(staff.pk)

        absent_list = [
            {
                "staff_id": emp.pk,
                "employee_id": emp.employee_id,
                "name": emp.full_name,
                "department": emp.department,
            }
            for emp in Staff.objects.all()
            if emp.pk not in present_staff_ids
        ]

        return Response({
            "date": str(report_date),
            "attendance": AttendanceSerializer(records, many=True).data,
            "absent": absent_list,
            "totals": {
                "present": records.filter(status=Attendance.STATUS_PRESENT).count()
                or records.filter(check_in__isnull=False, status=Attendance.STATUS_PRESENT).count()
                or records.filter(check_in__isnull=False).exclude(status=Attendance.STATUS_LATE).count(),
                "late": records.filter(status=Attendance.STATUS_LATE).count(),
                "absent": len(absent_list),
            },
        })
