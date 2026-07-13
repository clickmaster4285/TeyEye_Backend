from django.urls import path

from .views import (
    JourneyCameraSightingsAPIView,
    JourneyIngestAPIView,
    JourneyLiveAPIView,
    JourneyMergeVisitorAPIView,
    JourneyPersonCameraCapturesAPIView,
    JourneyPersonDetailAPIView,
    JourneyPersonListAPIView,
    JourneyPersonTimelineAPIView,
    JourneyRecentEventsAPIView,
    JourneySummaryAPIView,
)

urlpatterns = [
    path("person-journey/ingest/", JourneyIngestAPIView.as_view(), name="person-journey-ingest"),
    path("person-journey/persons/", JourneyPersonListAPIView.as_view(), name="person-journey-persons"),
    path("person-journey/persons/<uuid:uuid>/", JourneyPersonDetailAPIView.as_view(), name="person-journey-person-detail"),
    path("person-journey/persons/<uuid:uuid>/timeline/", JourneyPersonTimelineAPIView.as_view(), name="person-journey-timeline"),
    path(
        "person-journey/persons/<uuid:uuid>/camera-captures/",
        JourneyPersonCameraCapturesAPIView.as_view(),
        name="person-journey-camera-captures",
    ),
    path("person-journey/live/", JourneyLiveAPIView.as_view(), name="person-journey-live"),
    path("person-journey/summary/", JourneySummaryAPIView.as_view(), name="person-journey-summary"),
    path("person-journey/camera-sightings/", JourneyCameraSightingsAPIView.as_view(), name="person-journey-camera-sightings"),
    path("person-journey/events/recent/", JourneyRecentEventsAPIView.as_view(), name="person-journey-recent-events"),
    path("person-journey/merge-visitor/", JourneyMergeVisitorAPIView.as_view(), name="person-journey-merge-visitor"),
]
