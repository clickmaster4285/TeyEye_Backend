"""Unit tests for attendance decision engine (no InsightFace/RTSP required)."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from users.attendance_service import AttendanceDecisionEngine, mark_attendance_for_staff
from users.models import Attendance, Staff, User


class AttendanceDecisionEngineTests(TestCase):
    def setUp(self):
        self.staff = Staff.objects.create(
            full_name="Test Staff",
            cnic="12345-1234567-1",
            address="Test",
            department="HR",
            designation="Officer",
            emergency_contact="0300-0000000",
        )

    @override_settings(ATTENDANCE_WORK_START="09:00", ATTENDANCE_LATE_AFTER="09:30")
    def test_determine_status_present_and_late(self):
        early = timezone.make_aware(datetime(2026, 7, 21, 8, 50))
        late = timezone.make_aware(datetime(2026, 7, 21, 9, 45))
        self.assertEqual(
            AttendanceDecisionEngine.determine_status(early),
            Attendance.STATUS_PRESENT,
        )
        self.assertEqual(
            AttendanceDecisionEngine.determine_status(late),
            Attendance.STATUS_LATE,
        )

    @override_settings(ATTENDANCE_MIN_CHECKOUT_AFTER_IN_MINUTES=1)
    def test_check_in_then_checkout_and_ignore_immediate(self):
        now = timezone.make_aware(datetime(2026, 7, 21, 9, 0))
        decision = AttendanceDecisionEngine.process_recognition(
            staff=self.staff,
            confidence=0.9,
            source=Attendance.SOURCE_WEBCAM,
            now=now,
        )
        self.assertEqual(decision["action"], "check_in")
        self.assertIsNotNone(decision["record"].check_in)

        ignored = AttendanceDecisionEngine.process_recognition(
            staff=self.staff,
            confidence=0.9,
            source=Attendance.SOURCE_WEBCAM,
            now=now + timedelta(seconds=30),
        )
        self.assertEqual(ignored["action"], "ignored")

        checkout = AttendanceDecisionEngine.process_recognition(
            staff=self.staff,
            confidence=0.88,
            source=Attendance.SOURCE_CCTV,
            now=now + timedelta(minutes=5),
        )
        self.assertEqual(checkout["action"], "check_out")
        self.assertIsNotNone(checkout["record"].check_out)

    def test_mark_attendance_for_staff_helper(self):
        action, record = mark_attendance_for_staff(
            self.staff, source=Attendance.SOURCE_MANUAL, confidence=1.0
        )
        self.assertEqual(action, "check_in")
        self.assertIsNotNone(record)
        self.assertEqual(record.source, Attendance.SOURCE_MANUAL)
