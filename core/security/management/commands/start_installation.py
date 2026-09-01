import os
from os.path import basename

import django
from django.core.management import BaseCommand

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django_tenants.utils import schema_context

from core.security.models import *
from core.tenant.models import Scheme, Domain, Plan
from django.contrib.auth.models import Permission
from core.pos.models import *
from core.rrhh.models import *


class Command(BaseCommand):
    help = "Allows to initiate the base software installation"

    def handle(self, *args, **options):
        scheme = Scheme.objects.create(name=settings.DEFAULT_SCHEMA, schema_name=settings.DEFAULT_SCHEMA)
        Domain.objects.create(domain=settings.DOMAIN, tenant=scheme, is_primary=True)
        with schema_context(scheme.schema_name):
            dashboard = Dashboard.objects.create(
                name='INVOICE PRO',
                author='William Jair Dávila Vargas',
                icon='fa-solid fa-file-invoice-dollar',
                layout=1,
                navbar='navbar-dark navbar-navy',
                sidebar='sidebar-dark-navy'
            )
            image_path = f'{settings.BASE_DIR}{settings.STATIC_URL}img/default/logo.png'
            dashboard.image.save(basename(image_path), content=File(open(image_path, 'rb')), save=False)
            dashboard.save()

            moduletype = ModuleType.objects.create(name='Seguridad', icon='fas fa-lock')
            print(f'insertado {moduletype.name}')

            Plan.objects.create(name='Ilimitado', quantity=0)
            Plan.objects.create(name='Estándar', quantity=25)
            Plan.objects.create(name='Avanzado', quantity=50)
            Plan.objects.create(name='Profesional', quantity=100)
            Plan.objects.create(name='Empresarial', quantity=1000)
            Plan.objects.create(name='Premium', quantity=10000)

            modules_data = [
                {
                    'name': 'Tipos de Módulos',
                    'url': '/security/module/type/',
                    'icon': 'fas fa-door-open',
                    'description': 'Permite administrar los tipos de módulos del sistema',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=ModuleType._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Módulos',
                    'url': '/security/module/',
                    'icon': 'fas fa-th-large',
                    'description': 'Permite administrar los módulos del sistema',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Module._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Grupos',
                    'url': '/security/group/',
                    'icon': 'fas fa-users',
                    'description': 'Permite administrar los grupos de usuarios del sistema',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Group._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Respaldos',
                    'url': '/security/database/backups/',
                    'icon': 'fas fa-database',
                    'description': 'Permite administrar los respaldos de base de datos',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=DatabaseBackups._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Conf. Dashboard',
                    'url': '/security/dashboard/update/',
                    'icon': 'fas fa-tools',
                    'description': 'Permite configurar los datos de la plantilla',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Dashboard._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Accesos',
                    'url': '/security/user/access/',
                    'icon': 'fas fa-user-secret',
                    'description': 'Permite administrar los accesos de los usuarios',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=UserAccess._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Usuarios',
                    'url': '/user/',
                    'icon': 'fas fa-user',
                    'description': 'Permite administrar a los administradores del sistema',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=User._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Cambiar password',
                    'url': '/user/update/password/',
                    'icon': 'fas fa-key',
                    'description': 'Permite cambiar tu password de tu cuenta',
                    'moduletype': None,
                    'permissions': None
                },
                {
                    'name': 'Editar perfil',
                    'url': '/user/update/profile/',
                    'icon': 'fas fa-user',
                    'description': 'Permite cambiar la información de tu cuenta',
                    'moduletype': None,
                    'permissions': None
                }
            ]

            moduletype = ModuleType.objects.create(name='Multitenant', icon='fas fa-toolbox')
            print(f'insertado {moduletype.name}')

            modules_data.extend([
                {
                    'name': 'Compañias',
                    'url': '/tenant/company/',
                    'icon': 'fas fa-building',
                    'description': 'Permite gestionar la información de la compañia',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Company._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Planes',
                    'url': '/tenant/plan/',
                    'icon': 'fas fa-file-invoice',
                    'description': 'Permite adminstrar los planes de la facturación',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Plan._meta.label.split('.')[1].lower()))
                }
            ])

            for module_data in modules_data:
                module = Module.objects.create(
                    module_type=module_data['moduletype'],
                    name=module_data['name'],
                    url=module_data['url'],
                    icon=module_data['icon'],
                    description=module_data['description']
                )
                if module_data['permissions']:
                    for permission in module_data['permissions']:
                        module.permissions.add(permission)
                print(f'insertado {module.name}')

            group = Group.objects.create(name='Administrador')
            print(f'insertado {group.name}')

            for module in Module.objects.all():
                GroupModule.objects.create(module=module, group=group)
                for permission in module.permissions.all():
                    group.permissions.add(permission)

            user = User.objects.create(
                names='William Jair Dávila Vargas',
                username='admin',
                email='davilawilliam93@gmail.com',
                is_active=True,
                is_superuser=True,
                is_staff=True
            )
            user.set_password('hacker94')
            user.save()
            user.groups.add(group)
            print(f'Bienvenido {user.names}')
