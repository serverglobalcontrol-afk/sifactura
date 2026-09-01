from django.urls import path

from core.marketing.views.home.views import *
from core.marketing.views.marketing_page.views import *
from core.marketing.views.promotion.views import *

urlpatterns = [
    # marketing page
    path('page/update/', MarketingPageUpdateView.as_view(), name='marketing_page_update'),
    # promotion
    path('promotion/', PromotionListView.as_view(), name='promotion_list'),
    path('promotion/add/', PromotionCreateView.as_view(), name='promotion_create'),
    path('promotion/update/<int:pk>/', PromotionUpdateView.as_view(), name='promotion_update'),
    path('promotion/delete/<int:pk>/', PromotionDeleteView.as_view(), name='promotion_delete'),
]
