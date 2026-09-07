from django.core.management import BaseCommand
from django_tenants.utils import schema_context

GROUP_NAME = 'Administrador'

MODULES = [
    {
        'name': 'Proveedor de Facturación Electrónica',
        'url': '/tenant/electronic-invoicing-provider/update/',
        'icon': 'fas fa-file-signature',
        'description': 'Permite editar los datos del proveedor del sistema exigidos por el SRI',
        'model_label': 'tenant.electronicinvoicingprovider',
    },
    {
        'name': 'Página Informativa',
        'url': '/marketing/page/update/',
        'icon': 'fas fa-globe',
        'description': 'Permite editar el contenido de la página informativa pública',
        'model_label': 'marketing.marketingpage',
    },
    {
        'name': 'Promociones',
        'url': '/marketing/promotion/',
        'icon': 'fas fa-bullhorn',
        'description': 'Permite administrar las promociones de la página informativa',
        'model_label': 'marketing.promotion',
    },
]


class Command(BaseCommand):
    help = (
        "Crea, en el esquema public, los módulos del superadmin agregados "
        "después de la instalación inicial (start_installation solo corre "
        "una vez) y los asigna al grupo 'Administrador': Proveedor de "
        "Facturación Electrónica, Página Informativa y Promociones. Seguro "
        "de volver a ejecutar."
    )

    def handle(self, *args, **options):
        from django.contrib.auth.models import Permission
        from core.security.models import Module, Group, GroupModule, ModuleType

        with schema_context('public'):
            moduletype = ModuleType.objects.filter(name='Multitenant').first()
            if not moduletype:
                self.stdout.write(self.style.ERROR("No existe el ModuleType 'Multitenant', se aborta"))
                return

            group = Group.objects.filter(name=GROUP_NAME).first()
            if not group:
                self.stdout.write(self.style.ERROR(f"No existe el grupo '{GROUP_NAME}' en public, se aborta"))
                return

            for data in MODULES:
                app_label, model_name = data['model_label'].split('.')
                permissions = list(Permission.objects.filter(content_type__app_label=app_label, content_type__model=model_name))

                module, created = Module.objects.get_or_create(
                    url=data['url'],
                    defaults={
                        'name': data['name'],
                        'module_type': moduletype,
                        'description': data['description'],
                        'icon': data['icon'],
                    },
                )
                if created:
                    for permission in permissions:
                        module.permissions.add(permission)
                    self.stdout.write(f"módulo '{module.name}' creado")

                if not GroupModule.objects.filter(module=module, group=group).exists():
                    GroupModule.objects.create(module=module, group=group)
                    for permission in permissions:
                        group.permissions.add(permission)
                    self.stdout.write(self.style.SUCCESS(f"acceso a '{module.name}' agregado al grupo {group.name}"))

        self.stdout.write(self.style.SUCCESS('Proceso completado'))
