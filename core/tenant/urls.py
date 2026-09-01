from django.urls import path

from core.tenant.views.company.views import *
from core.tenant.views.plan.views import *

urlpatterns = [
    # plan
    path('plan/', PlanListView.as_view(), name='plan_list'),
    path('plan/add/', PlanCreateView.as_view(), name='plan_create'),
    path('plan/update/<int:pk>/', PlanUpdateView.as_view(), name='plan_update'),
    path('plan/delete/<int:pk>/', PlanDeleteView.as_view(), name='plan_delete'),
    # company
    path('company/', CompanyListView.as_view(), name='company_list'),
    path('company/add/', CompanyCreateView.as_view(), name='company_create'),
    path('company/update/<int:pk>/', CompanyUpdateView.as_view(), name='company_update'),
    path('company/delete/<int:pk>/', CompanyDeleteView.as_view(), name='company_delete')
]
