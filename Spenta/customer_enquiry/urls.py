from django.urls import path
from customer_enquiry import views

# ADD THIS LINE - This is crucial for namespaced URLs
app_name = 'customer_enquiry'

urlpatterns = [
    path('', views.index, name='index'),
    path('submit/', views.customer_submit_view, name='submit'),
    path('thank-you/', views.thank_you, name='thank_you'),
]