import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.urls import reverse_lazy
from django.views.generic import TemplateView

from core.contabilidad.mixins import AccountingEnabledMixin
from core.contabilidad.models import Account, BankAccount, JournalEntry, SOURCE_TYPE
from core.contabilidad.services.posting import Line, PeriodClosed, UnbalancedEntry, create_manual_entry, post_pending, void_manual_entry
from core.contabilidad.views.base import json_response
from core.security.mixins import GroupPermissionMixin


def _can(request, codename):
    group = request.session.get('group')
    return group is not None and group.permissions.filter(codename=codename).exists()


class EntryListView(AccountingEnabledMixin, GroupPermissionMixin, TemplateView):
    template_name = 'contabilidad/entry/list.html'
    permission_required = 'view_journalentry'

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            action = request.POST['action']
            if action == 'search':
                queryset = JournalEntry.objects.all()
                start, end = request.POST.get('start_date'), request.POST.get('end_date')
                if start and end:
                    queryset = queryset.filter(date__range=(start, end))
                if request.POST.get('source_type'):
                    queryset = queryset.filter(source_type=request.POST['source_type'])
                if request.POST.get('status'):
                    queryset = queryset.filter(status=request.POST['status'])
                data = [i.toJSON() for i in queryset.order_by('-date', '-number')[:2000]]
            elif action == 'detail':
                entry = JournalEntry.objects.get(pk=request.POST['id'])
                data = entry.toJSON()
                data['lines'] = [i.toJSON() for i in entry.lines.select_related('account').order_by('id')]
            elif action == 'void':
                if not _can(request, 'add_journalentry'):
                    data['error'] = 'Tu perfil no cuenta con el permiso necesario para anular asientos.'
                else:
                    void_manual_entry(JournalEntry.objects.get(pk=request.POST['id']), request.POST.get('reason') or 'Anulado manualmente')
            elif action == 'post_pending':
                if not _can(request, 'add_journalentry'):
                    data['error'] = 'Tu perfil no cuenta con el permiso necesario para contabilizar.'
                else:
                    start = datetime.strptime(request.POST['start_date'], '%Y-%m-%d').date()
                    end = datetime.strptime(request.POST['end_date'], '%Y-%m-%d').date()
                    if end < start:
                        raise ValueError('La fecha final no puede ser menor a la inicial.')
                    summary, errors = post_pending(start, end)
                    data = {'summary': summary, 'errors': errors[:20], 'errors_total': len(errors)}
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except (PeriodClosed, ValueError) as e:
            data['error'] = str(e)
        except Exception as e:
            data['error'] = str(e)
        return json_response(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Asientos Contables'
        context['create_url'] = reverse_lazy('contabilidad_entry_create')
        context['source_types'] = SOURCE_TYPE
        context['can_post'] = _can(self.request, 'add_journalentry')
        return context


class EntryCreateView(AccountingEnabledMixin, GroupPermissionMixin, TemplateView):
    """Asiento manual (apertura, ajustes, aportes...): líneas dinámicas que
    deben cuadrar exactamente."""
    template_name = 'contabilidad/entry/create.html'
    permission_required = 'add_journalentry'

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            if request.POST['action'] != 'add':
                raise ValueError('No ha seleccionado ninguna opción')
            entry_date = datetime.strptime(request.POST['date'], '%Y-%m-%d').date()
            description = (request.POST.get('description') or '').strip()
            if not description:
                raise ValueError('La descripción es obligatoria.')
            lines = []
            for item in json.loads(request.POST['lines']):
                account = Account.objects.get(pk=item['account'], accepts_movement=True, active=True)
                try:
                    debit = Decimal(str(item.get('debit') or 0)).quantize(Decimal('0.01'))
                    credit = Decimal(str(item.get('credit') or 0)).quantize(Decimal('0.01'))
                except InvalidOperation:
                    raise ValueError('Hay un valor no numérico en las líneas.')
                if debit < 0 or credit < 0 or (debit > 0 and credit > 0):
                    raise ValueError('Cada línea debe tener un valor en el Debe o en el Haber (no en ambos).')
                bank = None
                if hasattr(account, 'bank_account'):
                    bank = account.bank_account
                lines.append(Line(account=account, debit=debit, credit=credit, description=item.get('description') or '', bank_account=bank))
            entry = create_manual_entry(entry_date, description, lines, user=request.user)
            data['entry'] = str(entry)
        except Account.DoesNotExist:
            data['error'] = 'Una de las cuentas no existe, está inactiva o no acepta movimientos.'
        except (UnbalancedEntry, PeriodClosed, ValueError) as e:
            data['error'] = str(e)
        except Exception as e:
            data['error'] = str(e)
        return json_response(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Nuevo asiento manual'
        context['list_url'] = reverse_lazy('contabilidad_entry_list')
        context['action'] = 'add'
        context['accounts'] = Account.objects.filter(accepts_movement=True, active=True).order_by('code')
        return context
