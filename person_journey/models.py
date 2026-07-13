"""Tek Eye Person Journey — enterprise cross-camera person tracking."""

from __future__ import annotations

import uuid

from django.db import models


class PersonType(models.TextChoices):
    STAFF = "staff", "Staff"
    VISITOR = "visitor", "Visitor"
    UNKNOWN = "unknown", "Unknown"


class PersonStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    FINISHED = "finished", "Finished"
    MERGED = "merged", "Merged"


class TrackStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    FINISHED = "finished", "Finished"


class JourneyEventType(models.TextChoices):
    CAMERA_DETECTION = "camera_detection", "Camera Detection"
    STAFF_RECOGNIZED = "staff_recognized", "Staff Recognized"
    ATTENDANCE_CHECK_IN = "attendance_check_in", "Attendance Check-In"
    ATTENDANCE_CHECK_OUT = "attendance_check_out", "Attendance Check-Out"
    ZONE_ENTRY = "zone_entry", "Zone Entry"
    ZONE_EXIT = "zone_exit", "Zone Exit"
    WEAPON_DETECTED = "weapon_detected", "Weapon Detected"
    WATCHLIST = "watchlist", "Watchlist"
    PANIC = "panic", "Panic"
    UNKNOWN_CREATED = "unknown_created", "Unknown Person Created"
    PERSON_MERGED = "person_merged", "Person Merged"
    FACE_MATCHED = "face_matched", "Face Matched"
    ALERT = "alert", "Alert"


class JourneyPerson(models.Model):
    """Global person identity (P100 staff, V55 visitor, U300 unknown)."""

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    code = models.CharField(max_length=32, unique=True, db_index=True)
    person_type = models.CharField(
        max_length=16,
        choices=PersonType.choices,
        default=PersonType.UNKNOWN,
        db_index=True,
    )
    display_name = models.CharField(max_length=200, blank=True, default="")
    staff = models.ForeignKey(
        "users.Staff",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journey_persons",
    )
    visitor = models.ForeignKey(
        "visitors.Visitor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journey_persons",
    )
    face_embedding = models.JSONField(default=list, blank=True)
    reid_embedding = models.JSONField(default=list, blank=True)
    latest_camera = models.ForeignKey(
        "cameras.Camera",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journey_persons_latest",
    )
    latest_zone = models.CharField(max_length=64, blank=True, default="")
    latest_seen_at = models.DateTimeField(null=True, blank=True, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=PersonStatus.choices,
        default=PersonStatus.ACTIVE,
        db_index=True,
    )
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merged_from",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-latest_seen_at", "-created_at"]
        indexes = [
            models.Index(fields=["person_type", "status", "-latest_seen_at"]),
        ]

    def __str__(self):
        label = self.display_name or self.code
        return f"{label} ({self.person_type})"


class CameraTrack(models.Model):
    """ByteTrack session on a single camera."""

    journey_person = models.ForeignKey(
        JourneyPerson,
        on_delete=models.CASCADE,
        related_name="tracks",
    )
    camera = models.ForeignKey(
        "cameras.Camera",
        on_delete=models.CASCADE,
        related_name="journey_tracks",
    )
    track_id = models.PositiveIntegerField()
    status = models.CharField(
        max_length=16,
        choices=TrackStatus.choices,
        default=TrackStatus.ACTIVE,
        db_index=True,
    )
    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    last_bbox = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["camera", "track_id", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["camera", "track_id", "started_at"],
                name="person_journey_unique_camera_track_start",
            ),
        ]

    def __str__(self):
        return f"Track {self.track_id} @ {self.camera_id} → {self.journey_person.code}"


class JourneyEvent(models.Model):
    """Timeline entry for a person journey."""

    journey_person = models.ForeignKey(
        JourneyPerson,
        on_delete=models.CASCADE,
        related_name="events",
    )
    event_type = models.CharField(max_length=32, choices=JourneyEventType.choices, db_index=True)
    title = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    camera = models.ForeignKey(
        "cameras.Camera",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journey_events",
    )
    zone = models.CharField(max_length=64, blank=True, default="")
    gate = models.CharField(max_length=64, blank=True, default="")
    track = models.ForeignKey(
        CameraTrack,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    detection_event_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    zone_access_log_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    attendance_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    confidence = models.FloatField(null=True, blank=True)
    match_score = models.FloatField(null=True, blank=True)
    bbox = models.JSONField(default=list, blank=True)
    snapshot_path = models.CharField(max_length=512, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["journey_person", "-created_at"]),
            models.Index(fields=["event_type", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.journey_person.code} — {self.event_type} @ {self.created_at:%H:%M:%S}"
