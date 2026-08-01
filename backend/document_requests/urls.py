from django.urls import path
from . import views

# NOTE: no bare '' route here for list_create_view -- Next.js strips the
# trailing slash on /api/requests/ before its rewrite proxy even runs, so
# Django would only ever see the no-slash form. That route is registered
# directly in config/urls.py instead. Sub-paths below are fine since they're
# never empty strings.
urlpatterns = [
    path('validate', views.validate_view),
    path('checklist-template', views.checklist_template_view),
    path('<int:request_id>/resend', views.resend_view),
    path('<int:request_id>/email', views.latest_email_view),
    path('<int:request_id>/uploads', views.uploaded_files_view),
    path('<int:request_id>/uploads/<int:upload_id>/serve', views.serve_uploaded_file_view),
    path('<int:request_id>/parking-bay', views.parking_bay_view),
    path('<int:request_id>/parking-bay/<int:checklist_item_id>/review', views.review_checklist_item_view),
    path('<int:request_id>/parking-bay/send-flags-email', views.send_review_flags_email_view),
    path('<int:request_id>/parking-bay/kick-start-extraction', views.kick_start_extraction_view),
    path('<int:request_id>/extraction', views.extraction_view),
    path('<int:request_id>/extraction/<int:twin_id>/advance', views.advance_document_twin_view),
    path('<int:request_id>/business-twin/advance', views.advance_business_twin_view),
]
