from __future__ import annotations


import json

from typing import Any


from django.db import transaction

from django.shortcuts import get_object_or_404

from rest_framework import permissions, status

from rest_framework.response import Response

from rest_framework.views import APIView


from .models import DepositAccountEntry, DetentionMemo, DetentionMemoAttachment, DetentionMemoGoodsImage, DetentionMemoGoodsLine

from .serializers import (

    DepositAccountWriteSerializer,

    DetentionMemoWriteSerializer,

    apply_partial_to_deposit_entry,

    apply_validated_to_memo,

    create_deposit_account_entry,

    deposit_entry_to_frontend_dict,

    memo_to_frontend_dict,

    replace_goods_lines,

)

from .image_utils import compress_image


def _body_from_request(request) -> dict[str, Any]:

    ct = (request.content_type or "").lower()

    if "multipart/form-data" in ct:

        raw = request.data.get("payload")

        if raw is None or raw == "":

            return {}

        if isinstance(raw, dict):

            return dict(raw)

        if isinstance(raw, str):

            try:

                return json.loads(raw)

            except json.JSONDecodeError:

                return {}

        return {}

    if isinstance(request.data, dict):

        return dict(request.data)

    try:

        return dict(request.data)

    except Exception:

        return {}


def _save_memo_uploaded_media(request, memo: DetentionMemo) -> None:
    """Persist owner/driver FileFields and uploaded document/video attachments."""

    update_fields = []

    if request.FILES.get("owner_photo"):
        owner_photo = request.FILES["owner_photo"]
        # Compress image before saving
        owner_photo = compress_image(
            owner_photo, max_width=1920, max_height=1080, quality=85)
        memo.owner_photo_upload = owner_photo

        update_fields.append("owner_photo_upload")

    if request.FILES.get("driver_photo"):
        driver_photo = request.FILES["driver_photo"]
        # Compress image before saving
        driver_photo = compress_image(
            driver_photo, max_width=1920, max_height=1080, quality=85)
        memo.driver_photo_upload = driver_photo

        update_fields.append("driver_photo_upload")

    if update_fields:

        memo.save(update_fields=update_fields)

    for f in request.FILES.getlist("documents"):

        DetentionMemoAttachment.objects.create(

            memo=memo,

            kind=DetentionMemoAttachment.KIND_DOCUMENT,

            file=f,

            original_filename=(f.name or "")[:255],

        )

    for f in request.FILES.getlist("videos"):

        DetentionMemoAttachment.objects.create(

            memo=memo,

            kind=DetentionMemoAttachment.KIND_VIDEO,

            file=f,

            original_filename=(f.name or "")[:255],

        )


def _save_goods_images(request, memo: DetentionMemo, goods_items: list | None) -> None:
    """Save goods images uploaded for each goods line item."""
    if not goods_items:
        return

    for item in goods_items:
        client_line_id = item.get("id") or ""
        goods_line = DetentionMemoGoodsLine.objects.filter(
            memo=memo,
            client_line_id=client_line_id
        ).first()
        if not goods_line:
            continue

        existing_image_count = goods_line.images.count()
        remaining_slots = 10 - existing_image_count

        if remaining_slots <= 0:
            continue

        image_prefix = f"goods_image_{client_line_id}_"
        new_images = []
        for key in request.FILES:
            if key.startswith(image_prefix):
                if remaining_slots > 0:
                    img_file = request.FILES[key]
                    compressed = compress_image(
                        img_file, max_width=1920, max_height=1080, quality=85)
                    new_images.append(compressed)
                    remaining_slots -= 1

        for img_file in new_images:
            DetentionMemoGoodsImage.objects.create(
                goods_line=goods_line,
                image=img_file,
            )


def get_memo_queryset():

    return (

        DetentionMemo.objects.prefetch_related(
            "goods_lines__images", "attachments").all()

    )


class DetentionMemoListAPIView(APIView):

    """GET /api/detention-memos/list/"""

    permission_classes = [permissions.AllowAny]

    def get(self, request):

        memos = get_memo_queryset().order_by("-created_at")

        data = [memo_to_frontend_dict(m, request) for m in memos]

        return Response(data)


class DetentionMemoCreateAPIView(APIView):

    """POST /api/detention-memos/create/ (JSON or multipart/form-data with `payload` + files)."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):

        body = _body_from_request(request)

        ser = DetentionMemoWriteSerializer(data=body)

        ser.is_valid(raise_exception=True)

        validated = ser.validated_data

        with transaction.atomic():

            memo = DetentionMemo()

            apply_validated_to_memo(memo, validated)

            memo.save()

            replace_goods_lines(memo, validated.get("goodsItems"))

            _save_memo_uploaded_media(request, memo)

            _save_goods_images(request, memo, validated.get("goodsItems"))

            memo.refresh_from_db()

        base = (validated.get("clientOrigin") or "").strip() or request.build_absolute_uri("/").rstrip(

            "/"

        )

        update_fields = []

        if not (memo.memo_qr_code_payload or "").strip():

            memo.memo_qr_code_payload = f"{base}/detention-memo/{memo.pk}?print=full"

            update_fields.append("memo_qr_code_payload")

        if not (memo.memo_qr_code_number or "").strip():

            memo.memo_qr_code_number = f"DM-MEMO-{str(memo.pk).replace('-', '')[:12].upper()}"

            update_fields.append("memo_qr_code_number")

        if update_fields:

            memo.save(update_fields=update_fields)

        return Response(memo_to_frontend_dict(memo, request), status=status.HTTP_201_CREATED)


class DetentionMemoReadAPIView(APIView):

    """GET /api/detention-memos/<uuid:pk>/read/"""

    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):

        memo = get_object_or_404(get_memo_queryset(), pk=pk)

        return Response(memo_to_frontend_dict(memo, request))


class DetentionMemoUpdateAPIView(APIView):

    """PUT /api/detention-memos/<uuid:pk>/update/ — full replacement + optional extra files appended."""

    permission_classes = [permissions.AllowAny]

    def put(self, request, pk):

        memo = get_object_or_404(DetentionMemo.objects.all(), pk=pk)

        body = _body_from_request(request)

        ser = DetentionMemoWriteSerializer(data=body)

        ser.is_valid(raise_exception=True)

        validated = ser.validated_data

        with transaction.atomic():

            apply_validated_to_memo(memo, validated)

            memo.save()

            replace_goods_lines(memo, validated.get("goodsItems"))

            _save_memo_uploaded_media(request, memo)

            _save_goods_images(request, memo, validated.get("goodsItems"))

            memo.refresh_from_db()

        return Response(memo_to_frontend_dict(memo, request))


class DetentionMemoDeleteAPIView(APIView):

    """DELETE /api/detention-memos/<uuid:pk>/delete/"""

    permission_classes = [permissions.AllowAny]

    def delete(self, request, pk):

        memo = get_object_or_404(DetentionMemo.objects.all(), pk=pk)

        memo.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class DepositAccountEntryListAPIView(APIView):

    """GET /api/deposit-accounts/list/"""

    permission_classes = [permissions.AllowAny]

    def get(self, request):

        qs = DepositAccountEntry.objects.select_related(
            "detention_memo").all().order_by("-created_at")

        return Response([deposit_entry_to_frontend_dict(e) for e in qs])


class DepositAccountEntryCreateAPIView(APIView):

    """POST /api/deposit-accounts/create/"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):

        ser = DepositAccountWriteSerializer(data=request.data)

        ser.is_valid(raise_exception=True)

        entry = create_deposit_account_entry(ser.validated_data)

        entry.refresh_from_db()

        return Response(deposit_entry_to_frontend_dict(entry), status=status.HTTP_201_CREATED)


class DepositAccountEntryReadAPIView(APIView):

    """GET /api/deposit-accounts/<uuid:pk>/read/"""

    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):

        entry = get_object_or_404(

            DepositAccountEntry.objects.select_related("detention_memo"),

            pk=pk,

        )

        return Response(deposit_entry_to_frontend_dict(entry))


class DepositAccountEntryUpdateAPIView(APIView):

    """PATCH /api/deposit-accounts/<uuid:pk>/update/ — partial update (camelCase)."""

    permission_classes = [permissions.AllowAny]

    def patch(self, request, pk):

        entry = get_object_or_404(
            DepositAccountEntry.objects.select_related("detention_memo"), pk=pk)

        if not isinstance(request.data, dict):

            return Response({"detail": "Expected JSON object."}, status=status.HTTP_400_BAD_REQUEST)

        apply_partial_to_deposit_entry(entry, dict(request.data))

        entry.save()

        entry.refresh_from_db()

        return Response(deposit_entry_to_frontend_dict(entry))


class DepositAccountEntryDeleteAPIView(APIView):

    """DELETE /api/deposit-accounts/<uuid:pk>/delete/"""

    permission_classes = [permissions.AllowAny]

    def delete(self, request, pk):

        entry = get_object_or_404(DepositAccountEntry.objects.all(), pk=pk)

        entry.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)
