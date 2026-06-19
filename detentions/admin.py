from django.contrib import admin

from .models import (
    DepositAccountEntry,
    DetentionMemo,
    DetentionMemoAttachment,
    DetentionMemoGoodsLine,
)


class DetentionMemoGoodsLineInline(admin.TabularInline):
    model = DetentionMemoGoodsLine
    extra = 0


class DetentionMemoAttachmentInline(admin.TabularInline):
    model = DetentionMemoAttachment
    extra = 0
    readonly_fields = ("uploaded_at",)


@admin.register(DepositAccountEntry)
class DepositAccountEntryAdmin(admin.ModelAdmin):
    list_display = (
        "treasury_challan_no",
        "deposit_type",
        "case_seizure_ref",
        "fir_no",
        "customs_station",
        "amount",
        "deposit_date",
        "status",
        "created_at",
    )
    list_filter = ("deposit_type", "status")
    search_fields = ("treasury_challan_no", "case_seizure_ref", "fir_no")
    raw_id_fields = ("detention_memo",)


@admin.register(DetentionMemo)
class DetentionMemoAdmin(admin.ModelAdmin):
    list_display = ("case_no", "reference_number", "directorate", "verification_status", "created_at")
    list_filter = ("verification_status", "directorate")
    search_fields = ("case_no", "reference_number", "fir_number")
    inlines = [DetentionMemoGoodsLineInline, DetentionMemoAttachmentInline]
