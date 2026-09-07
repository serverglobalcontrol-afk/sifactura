from django.core.management import BaseCommand
from django_tenants.utils import schema_context

from core.tenant.models import Company

GROUP_NAME = 'Administrador'

REPORT_MODULES = [
    {
        'name': 'Ventas',
        'url': '/reports/sale/',
        'icon': 'fas fa-chart-bar',
        'description': 'Permite ver los reportes de las ventas',
    },
    {
        'name': 'Ventas por Punto de Venta',
        'url': '/reports/sale/point-of-sale/',
        'icon': 'fas fa-cash-register',
        'description': 'Permite ver las ventas diarias de cada punto de venta, en general o filtrado por fechas y por punto de venta puntual',
    },
    {
        'name': 'Productos con Stock Bajo',
        'url': '/reports/product/low-stock/',
        'icon': 'fas fa-exclamation-triangle',
        'description': 'Permite ver los productos inventariados cuyo stock llegó al mínimo configurado o está en negativo',
    },
    {
        'name': 'Productos Más Vendidos',
        'url': '/reports/product/best-sellers/',
        'icon': 'fas fa-trophy',
        'description': 'Permite ver los productos más vendidos en un rango de fechas',
    },
    {
        'name': 'Ventas por Producto',
        'url': '/reports/product/sales/',
        'icon': 'fas fa-search-dollar',
        'description': 'Permite saber a quién se le vendió un producto (cliente, comprobante, fecha), o buscar por número de comprobante',
    },
    {
        'name': 'Compras',
        'url': '/reports/purchase/',
        'icon': 'fas fa-chart-bar',
        'description': 'Permite ver los reportes de las compras',
    },
    {
        'name': 'Gastos',
        'url': '/reports/expenses/',
        'icon': 'fas fa-chart-bar',
        'description': 'Permite ver los reportes de los gastos',
    },
    {
        'name': 'Cuentas por Pagar',
        'url': '/reports/debts/pay/',
        'icon': 'fas fa-chart-bar',
        'description': 'Permite ver los reportes de las cuentas por pagar',
    },
    {
        'name': 'Cuentas por Cobrar',
        'url': '/reports/ctas/collect/',
        'icon': 'fas fa-chart-bar',
        'description': 'Permite ver los reportes de las cuentas por cobrar',
    },
    {
        'name': 'Resultados',
        'url': '/reports/results/',
        'icon': 'fas fa-chart-bar',
        'description': 'Permite ver los reportes de pérdidas y ganancias',
    },
    {
        'name': 'Ganancias',
        'url': '/reports/earnings/',
        'icon': 'fas fa-chart-bar',
        'description': 'Permite ver los reportes de las ganancias',
    },
    {
        'name': 'Ganancia Diaria',
        'url': '/reports/earnings/daily/',
        'icon': 'fas fa-coins',
        'description': 'Permite ver la utilidad real por día (precio facturado según cliente vs. costo del producto)',
    },
    {
        'name': 'Horas Trabajadas',
        'url': '/reports/hours/',
        'icon': 'fas fa-chart-bar',
        'description': 'Permite ver el reporte de horas trabajadas, horas extras y valor de pago de los empleados',
    },
    {
        'name': 'Marcaciones por Empleado',
        'url': '/reports/hours/detail/',
        'icon': 'fas fa-user-clock',
        'description': 'Permite ver el detalle diario de marcaciones de un empleado, con atrasos y salidas anticipadas',
    },
]


class Command(BaseCommand):
    help = (
        "Crea los módulos de Reportes que faltan (los agregados después de la "
        "creación de la compañía, ya que create_base_modules() solo se "
        "ejecuta una vez) y los asigna al grupo 'Administrador' en las "
        "compañías que ya existían. Es seguro volver a ejecutarlo: si el "
        "módulo o la asignación ya existen, se omiten."
    )

    def handle(self, *args, **options):
        from core.security.models import Module, Group, GroupModule, ModuleType

        with schema_context('public'):
            companies = list(Company.objects.all())

        for company in companies:
            with schema_context(company.schema_name):
                moduletype, _ = ModuleType.objects.get_or_create(name='Reportes', defaults={'icon': 'fas fa-chart-pie'})
                group = Group.objects.filter(name=GROUP_NAME).first()
                if not group:
                    self.stdout.write(self.style.WARNING(f"{company.business_name}: no existe el grupo '{GROUP_NAME}', se omite"))
                    continue

                for data in REPORT_MODULES:
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
                        self.stdout.write(f"{company.business_name}: módulo '{module.name}' creado")

                    if GroupModule.objects.filter(module=module, group=group).exists():
                        continue
                    GroupModule.objects.create(module=module, group=group)
                    self.stdout.write(self.style.SUCCESS(f"{company.business_name}: acceso a '{module.name}' agregado al grupo {group.name}"))

        self.stdout.write(self.style.SUCCESS('Proceso completado'))
