from django.contrib import admin

from .models import (
    DetentionAssessment,
    NoteSheet,
    NoteSheetAttachment,
    NoteSheetItem,
    NoteSheetItemImage,
    RecoveryMemo,
    SeizureReport,
)

admin.site.register(NoteSheet)
admin.site.register(NoteSheetItem)
admin.site.register(NoteSheetItemImage)
admin.site.register(NoteSheetAttachment)
admin.site.register(DetentionAssessment)
admin.site.register(RecoveryMemo)
admin.site.register(SeizureReport)
