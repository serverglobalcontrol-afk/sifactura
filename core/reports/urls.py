from django.urls import path
from core.reports.views.sale_report.views import SaleReportView
from core.reports.views.sale_point_of_sale_report.views import SalePointOfSaleReportView
from core.reports.views.low_stock_report.views import LowStockReportView
from core.reports.views.best_sellers_report.views import BestSellersReportView
from core.reports.views.daily_earnings_report.views import DailyEarningsReportView
from core.reports.views.product_sales_report.views import ProductSalesReportView
from core.reports.views.purchase_report.views import PurchaseReportView
from core.reports.views.expenses_report.views import ExpensesReportView
from core.reports.views.debts_pay_report.views import DebtsPayReportView
from core.reports.views.ctas_collect_report.views import CtasCollectReportView
from core.reports.views.results_report.views import ResultsReportView
from core.reports.views.earnings_report.views import EarningsReportView
from core.reports.views.hours_report.views import HoursReportView, HoursReportPrintView, HoursDetailReportView, HoursDetailReportPrintView
from core.reports.views.canceled_vouchers_report.views import CanceledVouchersReportView

urlpatterns = [
    path('sale/', SaleReportView.as_view(), name='sale_report'),
    path('sale/point-of-sale/', SalePointOfSaleReportView.as_view(), name='sale_point_of_sale_report'),
    path('product/low-stock/', LowStockReportView.as_view(), name='low_stock_report'),
    path('product/best-sellers/', BestSellersReportView.as_view(), name='best_sellers_report'),
    path('earnings/daily/', DailyEarningsReportView.as_view(), name='daily_earnings_report'),
    path('product/sales/', ProductSalesReportView.as_view(), name='product_sales_report'),
    path('purchase/', PurchaseReportView.as_view(), name='purchase_report'),
    path('expenses/', ExpensesReportView.as_view(), name='expenses_report'),
    path('debts/pay/', DebtsPayReportView.as_view(), name='debts_pay_report'),
    path('ctas/collect/', CtasCollectReportView.as_view(), name='ctas_collect_report'),
    path('results/', ResultsReportView.as_view(), name='results_report'),
    path('earnings/', EarningsReportView.as_view(), name='earnings_report'),
    path('hours/', HoursReportView.as_view(), name='hours_report'),
    path('hours/print/', HoursReportPrintView.as_view(), name='hours_report_print'),
    path('hours/detail/', HoursDetailReportView.as_view(), name='hours_detail_report'),
    path('hours/detail/print/', HoursDetailReportPrintView.as_view(), name='hours_detail_report_print'),
    path('sale/canceled/', CanceledVouchersReportView.as_view(), name='canceled_vouchers_report'),
]
