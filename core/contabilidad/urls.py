from django.urls import path

from core.contabilidad.views.ats import ATSView
from core.contabilidad.views.reconciliation import ReconciliationDetailView, ReconciliationListView
from core.contabilidad.views.account import AccountCreateView, AccountDeleteView, AccountListView, AccountUpdateView
from core.contabilidad.views.bank import (
    BankAccountCreateView, BankAccountDeleteView, BankAccountListView, BankAccountUpdateView, BankAliasCreateView,
    BankAliasDeleteView, BankAliasListView, BankAliasUpdateView, BankMoveView,
)
from core.contabilidad.views.config import AccountingConfigView
from core.contabilidad.views.entry import EntryCreateView, EntryListView
from core.contabilidad.views.period import PeriodListView
from core.contabilidad.views.reports import (
    BalanceSheetReportView, BankReportView, IncomeStatementReportView, JournalReportView, LedgerReportView, TrialBalanceReportView,
)

urlpatterns = [
    path('config/', AccountingConfigView.as_view(), name='contabilidad_config'),
    path('account/', AccountListView.as_view(), name='contabilidad_account_list'),
    path('account/add/', AccountCreateView.as_view(), name='contabilidad_account_create'),
    path('account/update/<int:pk>/', AccountUpdateView.as_view(), name='contabilidad_account_update'),
    path('account/delete/<int:pk>/', AccountDeleteView.as_view(), name='contabilidad_account_delete'),
    path('bank/', BankAccountListView.as_view(), name='contabilidad_bank_list'),
    path('bank/add/', BankAccountCreateView.as_view(), name='contabilidad_bank_create'),
    path('bank/update/<int:pk>/', BankAccountUpdateView.as_view(), name='contabilidad_bank_update'),
    path('bank/delete/<int:pk>/', BankAccountDeleteView.as_view(), name='contabilidad_bank_delete'),
    path('bank/alias/', BankAliasListView.as_view(), name='contabilidad_bank_alias_list'),
    path('bank/alias/add/', BankAliasCreateView.as_view(), name='contabilidad_bank_alias_create'),
    path('bank/alias/update/<int:pk>/', BankAliasUpdateView.as_view(), name='contabilidad_bank_alias_update'),
    path('bank/alias/delete/<int:pk>/', BankAliasDeleteView.as_view(), name='contabilidad_bank_alias_delete'),
    path('bank/move/', BankMoveView.as_view(), name='contabilidad_bank_move'),
    path('entry/', EntryListView.as_view(), name='contabilidad_entry_list'),
    path('entry/add/', EntryCreateView.as_view(), name='contabilidad_entry_create'),
    path('period/', PeriodListView.as_view(), name='contabilidad_period_list'),
    path('ats/', ATSView.as_view(), name='contabilidad_ats'),
    path('reconciliation/', ReconciliationListView.as_view(), name='contabilidad_reconciliation_list'),
    path('reconciliation/<int:pk>/', ReconciliationDetailView.as_view(), name='contabilidad_reconciliation_detail'),
    path('report/journal/', JournalReportView.as_view(), name='contabilidad_report_journal'),
    path('report/ledger/', LedgerReportView.as_view(), name='contabilidad_report_ledger'),
    path('report/trial/', TrialBalanceReportView.as_view(), name='contabilidad_report_trial'),
    path('report/balance/', BalanceSheetReportView.as_view(), name='contabilidad_report_balance'),
    path('report/income/', IncomeStatementReportView.as_view(), name='contabilidad_report_income'),
    path('report/bank/', BankReportView.as_view(), name='contabilidad_report_bank'),
]
