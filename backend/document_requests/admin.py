from django.contrib import admin
from .models import (
    DocumentRequest, RequestEmail, ChecklistItem, UploadedFile, UploadSession,
    DocumentTwin, BusinessTwin, ExtractionEvent, ExtractedValue, ChecklistPreference,
)


class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 0
    readonly_fields = ('name', 'category', 'audience', 'order', 'status', 'current_file')


@admin.register(DocumentRequest)
class DocumentRequestAdmin(admin.ModelAdmin):
    list_display = ('borrower_name', 'company_name', 'status', 'created_by', 'created_at')
    list_filter = ('status',)
    inlines = [ChecklistItemInline]


@admin.register(RequestEmail)
class RequestEmailAdmin(admin.ModelAdmin):
    list_display = ('subject', 'to_email', 'kind', 'document_request', 'sent_at')
    list_filter = ('kind',)
    readonly_fields = [f.name for f in RequestEmail._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ('file_name', 'document_request', 'checklist_item', 'file_size', 'review_status', 'uploaded_at')
    list_filter = ('review_status',)
    readonly_fields = [f.name for f in UploadedFile._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(UploadSession)
class UploadSessionAdmin(admin.ModelAdmin):
    list_display = ('document_request', 'started_at', 'total_attempts', 'failed_attempts', 'fraud_flagged_at')
    list_filter = ('fraud_flagged_at',)


@admin.register(DocumentTwin)
class DocumentTwinAdmin(admin.ModelAdmin):
    list_display = ('uploaded_file', 'document_request', 'current_stage', 'classification_label', 'received_at')
    list_filter = ('current_stage',)
    readonly_fields = [f.name for f in DocumentTwin._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ExtractedValue)
class ExtractedValueAdmin(admin.ModelAdmin):
    list_display = ('field_name', 'value', 'document_twin', 'confidence')
    readonly_fields = [f.name for f in ExtractedValue._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(BusinessTwin)
class BusinessTwinAdmin(admin.ModelAdmin):
    list_display = ('document_request', 'current_stage', 'relationship_at')
    list_filter = ('current_stage',)
    readonly_fields = [f.name for f in BusinessTwin._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ExtractionEvent)
class ExtractionEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'document_request', 'document_twin', 'created_at')
    list_filter = ('event_type',)
    readonly_fields = [f.name for f in ExtractionEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ChecklistPreference)
class ChecklistPreferenceAdmin(admin.ModelAdmin):
    list_display = ('banker', 'updated_at')
