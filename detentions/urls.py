from django.urls import path

from .views import (
    DepositAccountEntryListAPIView,
    DepositAccountEntryCreateAPIView,
    DepositAccountEntryReadAPIView,
    DepositAccountEntryUpdateAPIView,
    DepositAccountEntryDeleteAPIView,
    DetentionMemoListAPIView,
    DetentionMemoCreateAPIView,
    DetentionMemoReadAPIView,
    DetentionMemoUpdateAPIView,
    DetentionMemoDeleteAPIView,
)

urlpatterns = [
    path("deposit-accounts/list/", DepositAccountEntryListAPIView.as_view(), name="deposit-account-list"),
    path("deposit-accounts/create/", DepositAccountEntryCreateAPIView.as_view(), name="deposit-account-create"),
    path("deposit-accounts/<uuid:pk>/read/", DepositAccountEntryReadAPIView.as_view(), name="deposit-account-read"),
    path("deposit-accounts/<uuid:pk>/update/", DepositAccountEntryUpdateAPIView.as_view(), name="deposit-account-update"),
    path("deposit-accounts/<uuid:pk>/delete/", DepositAccountEntryDeleteAPIView.as_view(), name="deposit-account-delete"),
    path("detention-memos/list/", DetentionMemoListAPIView.as_view(), name="detention-memo-list"),
    path("detention-memos/create/", DetentionMemoCreateAPIView.as_view(), name="detention-memo-create"),
    path("detention-memos/<uuid:pk>/read/", DetentionMemoReadAPIView.as_view(), name="detention-memo-read"),
    path("detention-memos/<uuid:pk>/update/", DetentionMemoUpdateAPIView.as_view(), name="detention-memo-update"),
    path("detention-memos/<uuid:pk>/delete/", DetentionMemoDeleteAPIView.as_view(), name="detention-memo-delete"),
]
