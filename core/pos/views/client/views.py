import json
from datetime import datetime
from io import BytesIO

import pandas as pd
import xlsxwriter
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, DeleteView, TemplateView
from django.views.generic.base import View

from config import settings
from core.pos.forms import ClientForm, Client, ClientUserForm, User
from core.pos.choices import IDENTIFICATION_TYPE, CUSTOMER_TYPE
from core.pos.utilities.sri import SRI
from core.pos.utilities.text import smart_title_case
from core.security.mixins import GroupModuleMixin, GroupPermissionMixin

# Para el import de Excel: nombre visible del tipo de identificación -> código
# interno (igual que IDENTIFICATION_TYPE, pero invertido y en minúsculas para
# comparar sin importar cómo lo haya escrito quien llena la plantilla).
IDENTIFICATION_TYPE_BY_NAME = {name.lower(): code for code, name in IDENTIFICATION_TYPE}
CUSTOMER_TYPE_CODES = {code for code, _ in CUSTOMER_TYPE}


class ClientListView(GroupPermissionMixin, TemplateView):
    template_name = 'client/list.html'
    permission_required = 'view_client'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                for i in Client.objects.filter():
                    data.append(i.toJSON())
            elif action == 'upload_excel':
                # Carga masiva: puede crear o sobrescribir muchos clientes de
                # una sola vez, a diferencia del alta uno por uno (que Punto
                # de Venta sí puede seguir haciendo normalmente). Reservado a
                # Administrador -se reutiliza view_cashregister, ya usado en
                # todo el sistema como el permiso que distingue a
                # Administrador (Dashboard, Reportes), en vez de crear un
                # permiso nuevo solo para esto.
                if not request.user.has_perm('pos.view_cashregister'):
                    raise Exception('Solo un Administrador puede importar clientes desde Excel.')
                with transaction.atomic():
                    archive = request.FILES['archive']

                    df = pd.read_excel(
                        archive,
                        engine='openpyxl',
                        dtype={
                            'Cédula/RUC': str,
                            'Teléfono': str,
                            'Código': str,
                        }
                    )
                    df = df.fillna('')

                    dnis = df['Cédula/RUC'].astype(str).tolist()
                    existing_clients = {
                        c.dni: c for c in Client.objects.filter(dni__in=dnis).select_related('user')
                    }

                    client_group = Group.objects.get(pk=settings.GROUPS['client'])

                    clients_to_update = []
                    users_to_update = []
                    new_rows = []

                    for _, record in df.iterrows():
                        dni = str(record['Cédula/RUC']).strip()
                        if not dni:
                            continue
                        names = smart_title_case(str(record['Nombres']).strip())
                        email = str(record['Email']).strip()
                        mobile = str(record['Teléfono']).strip()
                        address = str(record['Dirección']).strip()
                        client_code = str(record['Código']).strip() or None

                        identification_type = IDENTIFICATION_TYPE_BY_NAME.get(
                            str(record['Tipo de identificación']).strip().lower(), IDENTIFICATION_TYPE[0][0]
                        )
                        customer_type = str(record['Tipo de Precio (retail/wholesale/credit_card)']).strip()
                        if customer_type not in CUSTOMER_TYPE_CODES:
                            customer_type = CUSTOMER_TYPE[0][0]
                        send_email_invoice = str(record['¿Enviar email de factura?']).strip().lower() == 'si'

                        birthdate_raw = record['Fecha de nacimiento']
                        if isinstance(birthdate_raw, str):
                            birthdate = datetime.strptime(birthdate_raw, '%Y-%m-%d').date() if birthdate_raw else None
                        else:
                            # pandas ya lo parseó como Timestamp.
                            birthdate = birthdate_raw.date() if birthdate_raw != '' else None

                        client = existing_clients.get(dni)
                        if client:
                            client.user.names = names
                            client.user.email = email
                            users_to_update.append(client.user)

                            client.mobile = mobile
                            client.address = address
                            client.client_code = client_code
                            client.identification_type = identification_type
                            client.customer_type = customer_type
                            client.send_email_invoice = send_email_invoice
                            if birthdate:
                                client.birthdate = birthdate
                            clients_to_update.append(client)
                        else:
                            new_rows.append({
                                'dni': dni, 'names': names, 'email': email, 'mobile': mobile,
                                'address': address, 'client_code': client_code,
                                'identification_type': identification_type, 'customer_type': customer_type,
                                'send_email_invoice': send_email_invoice, 'birthdate': birthdate,
                            })

                    if users_to_update:
                        User.objects.bulk_update(users_to_update, ['names', 'email'], batch_size=1000)

                    if clients_to_update:
                        Client.objects.bulk_update(
                            clients_to_update,
                            ['mobile', 'address', 'client_code', 'identification_type', 'customer_type', 'send_email_invoice', 'birthdate'],
                            batch_size=1000
                        )

                    if new_rows:
                        new_users = User.objects.bulk_create([
                            User(
                                username=row['dni'],
                                names=row['names'],
                                email=row['email'],
                                password=make_password(row['dni']),
                            )
                            for row in new_rows
                        ], batch_size=1000)
                        # bulk_create en PostgreSQL ya devuelve los objetos con
                        # su id asignado, así que se pueden usar de inmediato
                        # para crear los Client y el M2M de grupo sin volver a
                        # consultar la base.
                        User.groups.through.objects.bulk_create([
                            User.groups.through(user_id=user.id, group_id=client_group.id)
                            for user in new_users
                        ], batch_size=1000)
                        Client.objects.bulk_create([
                            Client(
                                user=user,
                                dni=row['dni'],
                                mobile=row['mobile'],
                                address=row['address'],
                                client_code=row['client_code'],
                                identification_type=row['identification_type'],
                                customer_type=row['customer_type'],
                                send_email_invoice=row['send_email_invoice'],
                                birthdate=row['birthdate'] or datetime.now().date(),
                                created_by=request.user,
                            )
                            for user, row in zip(new_users, new_rows)
                        ], batch_size=1000)
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Clientes'
        context['create_url'] = reverse_lazy('client_create')
        return context


class ClientExportExcelView(GroupPermissionMixin, View):
    # Exporta el Excel completo con email/teléfono de TODOS los clientes:
    # se exige view_cashregister además de view_client para que, igual que
    # la importación masiva, quede reservado a Administrador.
    permission_required = ['view_client', 'view_cashregister']

    def get(self, request, *args, **kwargs):
        try:
            headers = {
                'Id': 10, 'Código': 15, 'Nombres': 45, 'Tipo de identificación': 20, 'Cédula/RUC': 18,
                'Teléfono': 15, 'Email': 30, 'Dirección': 40, 'Fecha de nacimiento': 18,
                'Tipo de Precio (retail/wholesale/credit_card)': 30, '¿Enviar email de factura?': 18,
            }
            output = BytesIO()
            workbook = xlsxwriter.Workbook(output)
            worksheet = workbook.add_worksheet('clientes')
            cell_format = workbook.add_format({'bold': True, 'align': 'center', 'border': 1})
            row_format = workbook.add_format({'align': 'center', 'border': 1})
            # Cédula/RUC, Teléfono y Código son todo-dígitos y pueden empezar
            # con cero (ej. cédulas de algunas provincias) -num_format '@' es
            # el "Texto" de Excel: sin esto, Excel los detecta como número al
            # abrir/editar el archivo y borra el cero inicial, lo que después
            # hace que esa fila se importe como un cliente DUPLICADO en vez
            # de actualizar al existente.
            text_format = workbook.add_format({'align': 'center', 'border': 1, 'num_format': '@'})
            index = 0
            for name, width in headers.items():
                worksheet.set_column(first_col=index, last_col=index, width=width)
                worksheet.write(0, index, name, cell_format)
                index += 1
            row = 1
            for client in Client.objects.select_related('user').all().order_by('id'):
                worksheet.write_number(row, 0, client.id, row_format)
                worksheet.write_string(row, 1, client.client_code or '', text_format)
                worksheet.write_string(row, 2, client.user.names or '', row_format)
                worksheet.write_string(row, 3, client.get_identification_type_display(), row_format)
                worksheet.write_string(row, 4, client.dni, text_format)
                worksheet.write_string(row, 5, client.mobile, text_format)
                worksheet.write_string(row, 6, client.user.email or '', row_format)
                worksheet.write_string(row, 7, client.address, row_format)
                worksheet.write_string(row, 8, client.birthdate_format(), row_format)
                worksheet.write_string(row, 9, client.customer_type, row_format)
                worksheet.write_string(row, 10, 'Si' if client.send_email_invoice else 'No', row_format)
                row += 1
            workbook.close()
            output.seek(0)
            response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f"attachment; filename=CLIENTES_{datetime.now().date().strftime('%d_%m_%Y')}.xlsx"
            return response
        except Exception as e:
            messages.error(request, str(e))
        return HttpResponseRedirect(reverse_lazy('client_list'))


class ClientCreateView(GroupPermissionMixin, CreateView):
    model = Client
    template_name = 'client/create.html'
    form_class = ClientForm
    success_url = reverse_lazy('client_list')
    permission_required = 'add_client'

    def get_form_user(self):
        form = ClientUserForm()
        if self.request.POST or self.request.FILES:
            form = ClientUserForm(self.request.POST, self.request.FILES)
        return form

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'add':
                with transaction.atomic():
                    form1 = self.get_form_user()
                    form2 = self.get_form()
                    if form1.is_valid() and form2.is_valid():
                        user = form1.save(commit=False)
                        user.username = form2.cleaned_data['dni']
                        user.set_password(user.username)
                        user.save()
                        user.groups.add(Group.objects.get(pk=settings.GROUPS['client']))
                        form_client = form2.save(commit=False)
                        form_client.user = user
                        form_client.created_by = request.user
                        form_client.save()
                    else:
                        if not form1.is_valid():
                            data['error'] = form1.errors
                        elif not form2.is_valid():
                            data['error'] = form2.errors
            elif action == 'validate_data':
                data = {'valid': True}
                pattern = request.POST['pattern']
                parameter = request.POST['parameter'].strip()
                queryset = Client.objects.all()
                if pattern == 'dni':
                    data['valid'] = not queryset.filter(dni=parameter).exists()
                elif pattern == 'mobile':
                    data['valid'] = not queryset.filter(mobile=parameter).exists()
                elif pattern == 'email':
                    data['valid'] = not queryset.filter(user__email=parameter).exists()
                elif pattern == 'client_code':
                    # Opcional: sin valor no hay nada que validar (varios
                    # clientes pueden no tener código).
                    data['valid'] = not parameter or not queryset.filter(client_code=parameter).exists()
            elif action == 'search_ruc_in_sri':
                data = SRI().search_ruc_in_sri(ruc=request.POST['dni'])
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Nuevo registro de un Cliente'
        context['list_url'] = self.success_url
        context['action'] = 'add'
        context['frmUser'] = self.get_form_user()
        return context


class ClientUpdateView(GroupPermissionMixin, UpdateView):
    model = Client
    template_name = 'client/create.html'
    form_class = ClientForm
    success_url = reverse_lazy('client_list')
    permission_required = 'change_client'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def get_form_user(self):
        form = ClientUserForm(instance=self.request.user)
        if self.request.POST or self.request.FILES:
            form = ClientUserForm(self.request.POST, self.request.FILES, instance=self.object.user)
        return form

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'edit':
                with transaction.atomic():
                    form1 = self.get_form_user()
                    form2 = self.get_form()
                    if form1.is_valid() and form2.is_valid():
                        user = form1.save(commit=False)
                        user.save()
                        form_client = form2.save(commit=False)
                        form_client.user = user
                        form_client.save()
                    else:
                        if not form1.is_valid():
                            data['error'] = form1.errors
                        elif not form2.is_valid():
                            data['error'] = form2.errors
            elif action == 'validate_data':
                data = {'valid': True}
                pattern = request.POST['pattern']
                parameter = request.POST['parameter'].strip()
                queryset = Client.objects.all().exclude(id=self.object.id)
                if pattern == 'dni':
                    data['valid'] = not queryset.filter(dni=parameter).exists()
                elif pattern == 'mobile':
                    data['valid'] = not queryset.filter(mobile=parameter).exists()
                elif pattern == 'email':
                    data['valid'] = not queryset.filter(user__email=parameter).exists()
                elif pattern == 'client_code':
                    data['valid'] = not parameter or not queryset.filter(client_code=parameter).exists()
            elif action == 'search_ruc_in_sri':
                data = SRI().search_ruc_in_sri(ruc=request.POST['dni'])
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Edición de un Cliente'
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        context['frmUser'] = ClientUserForm(instance=self.object.user)
        return context


class ClientDeleteView(GroupPermissionMixin, DeleteView):
    model = Client
    template_name = 'delete.html'
    success_url = reverse_lazy('client_list')
    permission_required = 'delete_client'

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            self.get_object().delete()
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Notificación de eliminación'
        context['list_url'] = self.success_url
        return context


class ClientUpdateProfileView(GroupModuleMixin, UpdateView):
    model = Client
    template_name = 'client/profile.html'
    form_class = ClientForm
    success_url = settings.LOGIN_REDIRECT_URL

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return self.request.user.client

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        for name in ['dni', 'identification_type', 'send_email_invoice', 'customer_type', 'client_code']:
            form.fields[name].widget.attrs['disabled'] = True
            form.fields[name].required = False
        return form

    def get_form_user(self):
        form = ClientUserForm(instance=self.request.user)
        if self.request.POST or self.request.FILES:
            form = ClientUserForm(self.request.POST, self.request.FILES, instance=self.request.user)
        for name in ['names']:
            form.fields[name].widget.attrs['readonly'] = True
            form.fields[name].required = False
        return form

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'edit':
                with transaction.atomic():
                    form1 = self.get_form_user()
                    form2 = self.get_form()
                    if form1.is_valid() and form2.is_valid():
                        user = form1.save(commit=False)
                        user.save()
                        form_client = form2.save(commit=False)
                        form_client.user = user
                        form_client.save()
                    else:
                        if not form1.is_valid():
                            data['error'] = form1.errors
                        elif not form2.is_valid():
                            data['error'] = form2.errors
            elif action == 'validate_data':
                data = {'valid': True}
                pattern = request.POST['pattern']
                parameter = request.POST['parameter'].strip()
                queryset = Client.objects.all().exclude(id=self.object.id)
                if pattern == 'dni':
                    data['valid'] = not queryset.filter(dni=parameter).exists()
                elif pattern == 'mobile':
                    data['valid'] = not queryset.filter(mobile=parameter).exists()
                elif pattern == 'email':
                    data['valid'] = not queryset.filter(user__email=parameter).exists()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Edición de Perfil'
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        context['frmUser'] = self.get_form_user()
        return context
