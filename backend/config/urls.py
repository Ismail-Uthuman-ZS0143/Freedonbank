from django.contrib import admin
from django.urls import path, include

from document_requests.views import list_create_view, upload_info_view, upload_document_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    # Exact no-trailing-slash match -- see the note in document_requests/urls.py.
    path('api/requests', list_create_view),
    path('api/requests/', include('document_requests.urls')),
    # Step 4: public (no-auth) upload portal, keyed by token, not id.
    path('api/upload/<str:token>', upload_info_view),
    path('api/upload/<str:token>/documents', upload_document_view),
]
