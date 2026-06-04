from django.urls import path
from bulk_upload import views

app_name = 'bulk_upload'

urlpatterns = [
    path('channel-partners/', views.cp_bulk_upload, name='cp_bulk_upload'),
    path('channel-partners/template/', views.download_template, name='cp_template'),
    path('channel-partners/error-report/', views.download_error_report, name='cp_error_report'),
    path('channel-partners/clear/', views.clear_results, name='cp_clear'),
]
