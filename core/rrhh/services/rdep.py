"""RDEP: Anexo de retenciones en la fuente de Impuesto a la Renta bajo relación de dependencia.

Este módulo reúne lo que NO depende de la base de datos para poder probarlo solo:
el cálculo del impuesto causado con la tabla anual (art. 36 LRTI) y la rebaja por
gastos personales (Ficha Técnica del SRI, sección 1.5). Los valores de cada año
(tabla, canasta familiar básica) se guardan en RdepYear / RdepTaxBracket y los
confirma el contador: aquí solo se SUGIEREN los del SRI para 2026.
"""
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal('0.01')
ZERO = Decimal('0.00')

# Canastas familiares básicas (múltiplos de la CFB) que limitan la rebaja, según el número de cargas.
BASKETS_BY_DEPENDENTS = {0: 7, 1: 9, 2: 11, 3: 14, 4: 17, 5: 20}
BASKETS_CATASTROPHIC = 100
REBATE_RATE = Decimal('0.18')

# Valores publicados por el SRI para el ejercicio 2026 (resolución NAC-DGERCGC25-00000043; canasta de
# enero 2026 según boletín del SRI). Son una SUGERENCIA para precargar: el contador debe confirmarlos.
SUGGESTED_YEARS = {
    2026: {
        'basic_basket': '821.80',
        'source': 'SRI: resolución NAC-DGERCGC25-00000043 (tabla 2026) y canasta familiar básica de enero 2026. Confirmar con el contador.',
        # (fracción básica, exceso hasta, impuesto fracción básica, % fracción excedente)
        'brackets': [
            ('0', '12208', '0', '0'), ('12208', '15549', '0', '5'), ('15549', '20188', '167', '10'), ('20188', '26700', '631', '12'),
            ('26700', '35136', '1412', '15'), ('35136', '46575', '2678', '20'), ('46575', '62005', '4965', '25'),
            ('62005', '82679', '8823', '30'), ('82679', '109956', '15025', '35'), ('109956', None, '24572', '37'),
        ],
    },
}


def money(value):
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def income_tax(base, brackets):
    """Impuesto causado = impuesto de la fracción básica + (base - fracción básica) x %.
    `brackets`: lista de dicts/objetos con lower, upper (None = sin límite), base_tax, rate."""
    base = money(base)
    if base <= 0:
        return ZERO
    chosen = None
    for bracket in sorted(brackets, key=lambda b: Decimal(str(_get(b, 'lower')))):
        if base > Decimal(str(_get(bracket, 'lower'))):
            chosen = bracket  # la última fracción cuyo inicio queda por debajo de la base
    if chosen is None:
        raise ValueError('La base imponible no entra en ninguna fracción de la tabla de impuesto: revisa los Parámetros del RDEP.')
    lower = Decimal(str(_get(chosen, 'lower')))
    return money(Decimal(str(_get(chosen, 'base_tax'))) + (base - lower) * Decimal(str(_get(chosen, 'rate'))) / Decimal('100'))


def personal_expenses_rebate(total_expenses, dependents, catastrophic, basic_basket, galapagos=False, galapagos_index=Decimal('1')):
    """Rebaja por gastos personales = 18% del MENOR entre el total de gastos y el tope
    (canasta familiar básica x canastas según cargas; 100 si es o tiene a cargo una
    persona con discapacidad o enfermedad catastrófica). En Galápagos el tope se
    multiplica por el IPCEG."""
    baskets = BASKETS_CATASTROPHIC if catastrophic else BASKETS_BY_DEPENDENTS[min(max(int(dependents), 0), 5)]
    cap = Decimal(str(basic_basket)) * baskets
    if galapagos:
        cap *= Decimal(str(galapagos_index))
    return money(min(money(total_expenses), cap) * REBATE_RATE)


def _get(item, name):
    return item[name] if isinstance(item, dict) else getattr(item, name)


# ======================================================================= PASO 2
# Cálculo por empleado, XML del anexo y revisión con avisos.
import io
import os
import re
import unicodedata
import zipfile

from lxml import etree

from core.pos.utilities.xsd import XSD_DIR

PAYROLL_FIELDS = ('suelSal', 'sobSuelComRemu', 'partUtil', 'decimTer', 'decimCuar', 'fondoReserva', 'salarioDigno',
                  'otrosIngRenGrav', 'apoPerIess', 'valRet')
MANUAL_FIELDS = (
    'expenses_housing', 'expenses_health', 'expenses_education', 'expenses_food', 'expenses_clothing', 'expenses_tourism',
    'other_employers_income', 'other_employers_iess', 'other_employers_tax', 'tax_assumed', 'exoneration_disability', 'exoneration_elderly',
)
_schema = None


class Issues:
    def __init__(self):
        self.items = []

    def add(self, level, document, message):
        self.items.append({'level': level, 'document': document, 'message': message})

    def error(self, document, message):
        self.add('error', document, message)

    def warning(self, document, message):
        self.add('warning', document, message)

    def info(self, document, message):
        self.add('info', document, message)

    @property
    def has_errors(self):
        return any(i['level'] == 'error' for i in self.items)


def clean_person_name(text):
    """El RDEP solo admite letras y espacios (la ñ va como n)."""
    text = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode('ascii').upper()
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z ]+', ' ', text)).strip()[:100]


def split_full_name(full_name):
    """'APELLIDO1 APELLIDO2 NOMBRE1 NOMBRE2' -> (apellidos, nombres); con pocas palabras se reparte lo posible."""
    words = clean_person_name(full_name).split()
    if len(words) >= 4:
        return ' '.join(words[:2]), ' '.join(words[2:])
    if len(words) == 3:
        return ' '.join(words[:2]), words[2]
    if len(words) == 2:
        return words[0], words[1]
    return (words[0], words[0]) if words else ('', '')


def compute_employee(person, amounts, manual, brackets, basic_basket, galapagos_index=Decimal('1')):
    """Cifras del RDEP de un empleado. `amounts`: lo que sale de la nómina del año (por casilla); `manual`:
    datos anuales que registra el usuario. Devuelve un dict con todos los campos numéricos del XML."""
    def d(value):
        return money(value)

    a = {code: d(amounts.get(code)) for code in PAYROLL_FIELDS}
    m = {code: d(manual.get(code)) for code in MANUAL_FIELDS}
    row = {
        'suelSal': a['suelSal'], 'sobSuelComRemu': a['sobSuelComRemu'], 'partUtil': a['partUtil'],
        'intGrabGen': m['other_employers_income'], 'impRentEmpl': m['tax_assumed'],
        'decimTer': a['decimTer'], 'decimCuar': a['decimCuar'], 'fondoReserva': a['fondoReserva'], 'salarioDigno': a['salarioDigno'],
        'otrosIngRenGrav': a['otrosIngRenGrav'],
        'apoPerIess': a['apoPerIess'], 'aporPerIessConOtrosEmpls': m['other_employers_iess'],
        'deducVivienda': m['expenses_housing'], 'deducSalud': m['expenses_health'], 'deducEducartcult': m['expenses_education'],
        'deducAliement': m['expenses_food'], 'deducVestim': m['expenses_clothing'], 'deduccionTurismo': m['expenses_tourism'],
        'exoDiscap': m['exoneration_disability'], 'exoTerEd': m['exoneration_elderly'],
        'valRetAsuOtrosEmpls': m['other_employers_tax'], 'valImpAsuEsteEmpl': m['tax_assumed'], 'valRet': a['valRet'],
    }
    ing = row['suelSal'] + row['sobSuelComRemu'] + row['partUtil']
    if str(person.get('net_salary')) == '2':
        ing += row['impRentEmpl']
    row['ingGravConEsteEmpl'] = ing
    row['basImp'] = max(ing + row['intGrabGen'] - row['apoPerIess'] - row['aporPerIessConOtrosEmpls'] - row['exoDiscap'] - row['exoTerEd'], ZERO)
    row['impRentCaus'] = income_tax(row['basImp'], brackets)
    total_expenses = sum((row[k] for k in ('deducVivienda', 'deducSalud', 'deducEducartcult', 'deducAliement', 'deducVestim', 'deduccionTurismo')), ZERO)
    rebate = personal_expenses_rebate(
        total_expenses, person.get('dependents', 0), str(person.get('catastrophic')) == 'SI', basic_basket,
        galapagos=str(person.get('galapagos')) == 'SI', galapagos_index=galapagos_index)
    row['rebajaGastosPersonales'] = min(rebate, row['impRentCaus'])
    row['impuestoRentaRebajaGastosPersonales'] = max(row['impRentCaus'] - row['rebajaGastosPersonales'], ZERO)
    row['expected_retention'] = max(row['impuestoRentaRebajaGastosPersonales'] - row['valRetAsuOtrosEmpls'] - row['valImpAsuEsteEmpl'], ZERO)
    return row


def _sub(parent, tag, text):
    node = etree.SubElement(parent, tag)
    node.text = str(text)
    return node


def _fmt(value):
    return f'{money(value):.2f}'


def render_xml(header, employees):
    """XML (bytes, ISO-8859-1 como el ejemplo del SRI). `header`: ruc, year, employer_type, social_security.
    `employees`: lista de {'person': {...}, 'row': {...}} ya calculados."""
    root = etree.Element('rdep')
    _sub(root, 'numRuc', header['ruc'])
    _sub(root, 'anio', header['year'])
    _sub(root, 'tipoEmpleador', header['employer_type'])
    _sub(root, 'enteSegSocial', header['social_security'])
    if employees:
        container = etree.SubElement(root, 'retRelDep')
        for item in employees:
            person, row = item['person'], item['row']
            record = etree.SubElement(container, 'datRetRelDep')
            emp = etree.SubElement(record, 'empleado')
            _sub(emp, 'benGalpg', person['galapagos'])
            _sub(emp, 'enfcatastro', person['catastrophic'])
            _sub(emp, 'numCargRebGastPers', person['dependents'])
            _sub(emp, 'tipIdRet', person['id_type'])
            _sub(emp, 'idRet', person['id_number'])
            _sub(emp, 'apellidoTrab', person['last_names'])
            _sub(emp, 'nombreTrab', person['first_names'])
            _sub(emp, 'estab', person['establishment'])
            _sub(emp, 'residenciaTrab', person['residence'])
            _sub(emp, 'paisResidencia', person['country'])
            _sub(emp, 'aplicaConvenio', person['treaty'])
            _sub(emp, 'tipoTrabajDiscap', person['disability'])
            _sub(emp, 'porcentajeDiscap', person['disability_percent'])
            _sub(emp, 'tipIdDiscap', person['disability_id_type'])
            _sub(emp, 'idDiscap', person['disability_id'])
            for tag in ('suelSal', 'sobSuelComRemu', 'partUtil', 'intGrabGen', 'impRentEmpl', 'decimTer', 'decimCuar', 'fondoReserva',
                        'salarioDigno', 'otrosIngRenGrav', 'ingGravConEsteEmpl'):
                _sub(record, tag, _fmt(row[tag]))
            _sub(record, 'sisSalNet', person['net_salary'])
            for tag in ('apoPerIess', 'aporPerIessConOtrosEmpls', 'deducVivienda', 'deducSalud', 'deducEducartcult', 'deducAliement',
                        'deducVestim', 'deduccionTurismo', 'exoDiscap', 'exoTerEd', 'basImp', 'impRentCaus', 'rebajaGastosPersonales',
                        'impuestoRentaRebajaGastosPersonales', 'valRetAsuOtrosEmpls', 'valImpAsuEsteEmpl', 'valRet'):
                _sub(record, tag, _fmt(row[tag]))
    data = etree.tostring(root, encoding='ISO-8859-1', xml_declaration=True, pretty_print=True)
    return data.replace(b"<?xml version='1.0' encoding='ISO-8859-1'?>", b'<?xml version="1.0" encoding="ISO-8859-1" standalone="yes"?>', 1)


def validate_xml(data):
    """Errores (str) contra el esquema oficial RDEP.xsd; lista vacía si cumple."""
    global _schema
    if _schema is None:
        _schema = etree.XMLSchema(etree.parse(os.path.join(XSD_DIR, 'RDEP.xsd')))
    document = etree.fromstring(data)
    if _schema.validate(document):
        return []
    return [f'línea {e.line}: {e.message}' for e in list(_schema.error_log)[:10]]


def build_zip(year, data):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f'RDEP{year}.xml', data)
    return buffer.getvalue()


# ----------------------------------------------------------- con base de datos
def person_of(employee, issues):
    """Datos de identificación del empleado para el XML, con lo que falte reportado como error/aviso."""
    document = f'Empleado {employee.get_full_name()}'
    id_type = employee.rdep_id_type
    number = (employee.dni or '').strip()
    if id_type == 'C' and not (len(number) == 10 and number.isdigit()):
        issues.error(document, f'La cédula "{number}" debe tener 10 dígitos (Recursos Humanos > Empleados).')
    if id_type != 'C' and not (3 <= len(number) <= 13 and number.isalnum()):
        issues.error(document, f'El documento "{number}" debe tener entre 3 y 13 letras o números.')
    last, first = employee.rdep_last_names, employee.rdep_first_names
    if not (last and first):
        guessed_last, guessed_first = split_full_name(employee.user.names)
        last, first = clean_person_name(last) or guessed_last, clean_person_name(first) or guessed_first
        issues.info(document, f'Apellidos y nombres separados automáticamente: {last} / {first}. Confírmalo en el empleado (datos del RDEP).')
    last, first = clean_person_name(last), clean_person_name(first)
    if len(last) < 2 or len(first) < 2:
        issues.error(document, 'Faltan los apellidos o los nombres del empleado (mínimo 2 letras cada uno).')
    disability = employee.rdep_disability
    if disability == '01':
        disability_type, disability_id, percent = 'N', '999', 0
    else:
        percent = int(employee.rdep_disability_percent or 0)
        if percent <= 0:
            issues.error(document, 'Indicaste una condición de discapacidad: escribe el porcentaje de discapacidad.')
        if disability == '02':
            disability_type, disability_id = 'N', '999'
        else:
            disability_id = (employee.rdep_dependents_id or '').strip()
            if not (3 <= len(disability_id) <= 13):
                issues.error(document, 'Escribe la identificación de la persona con discapacidad a su cargo o a quien sustituye.')
            disability_type = 'C' if len(disability_id) == 10 and disability_id.isdigit() else 'P'
    if employee.rdep_residence == '02' and employee.rdep_country == '593':
        issues.warning(document, 'Es residente en el exterior pero el país es Ecuador (593): revisa el país de residencia.')
    return {
        'id_type': id_type, 'id_number': number, 'last_names': last, 'first_names': first, 'establishment': employee.rdep_establishment,
        'residence': employee.rdep_residence, 'country': employee.rdep_country, 'treaty': employee.rdep_treaty,
        'disability': disability, 'disability_percent': percent, 'disability_id_type': disability_type, 'disability_id': disability_id or '999',
        'dependents': int(employee.rdep_dependents), 'galapagos': employee.rdep_galapagos, 'catastrophic': employee.rdep_catastrophic,
        'net_salary': employee.rdep_net_salary,
    }


def build_year(company, year):
    """Calcula el RDEP del año con la nómina y los datos anuales. Devuelve (xml_bytes, resumen)."""
    from core.rrhh.models import Employee, RdepEmployeeYear, RdepYear, SalaryDetail, SalaryHeadings
    issues = Issues()
    params = RdepYear.objects.filter(year=year).first()
    if params is None:
        raise ValueError(f'Faltan los parámetros del RDEP {year} (tabla de impuesto y canasta familiar básica): cárgalos en Recursos Humanos > Parámetros RDEP.')
    brackets = [{'lower': b.lower, 'upper': b.upper, 'base_tax': b.base_tax, 'rate': b.rate} for b in params.brackets.all()]
    if not brackets:
        raise ValueError(f'Los parámetros del RDEP {year} no tienen la tabla del impuesto a la renta.')
    if not (len(company.ruc or '') == 13 and company.ruc.isdigit() and company.ruc.endswith('001')):
        issues.error('Empresa', f'El RUC de la empresa ({company.ruc}) debe tener 13 dígitos y terminar en 001.')

    employees, table = [], []
    unmapped = {}
    with_payroll = set(SalaryDetail.objects.filter(salary__year=year).values_list('employee_id', flat=True))
    manual_by_employee = {x.employee_id: x for x in RdepEmployeeYear.objects.filter(year=year)}
    for employee in Employee.objects.select_related('user').order_by('code'):
        if employee.pk not in with_payroll:
            continue
        document = f'Empleado {employee.get_full_name()}'
        amounts = {code: ZERO for code in PAYROLL_FIELDS}
        for line in SalaryHeadings.objects.filter(salary_detail__employee=employee, salary_detail__salary__year=year).select_related('headings'):
            value = Decimal(line.valor)
            if line.headings.rdep_field in amounts:
                amounts[line.headings.rdep_field] += value
            elif value > 0:
                unmapped.setdefault(line.headings.name, ZERO)
                unmapped[line.headings.name] += value
        manual_item = manual_by_employee.get(employee.pk)
        manual = {code: getattr(manual_item, code, ZERO) if manual_item else ZERO for code in MANUAL_FIELDS}
        person = person_of(employee, issues)
        try:
            row = compute_employee(person, amounts, manual, brackets, params.basic_basket, params.galapagos_index)
        except ValueError as e:
            issues.error(document, str(e))
            continue
        if row['ingGravConEsteEmpl'] <= 0:
            issues.warning(document, 'Tiene nómina en el año pero ninguna casilla de ingresos gravados: revisa que sus rubros estén asignados a una casilla del RDEP (Rubros).')
        if row['ingGravConEsteEmpl'] > 0 and row['apoPerIess'] <= 0:
            issues.warning(document, 'No tiene aporte personal al IESS en el año: revisa el rubro del descuento al IESS.')
        if abs(row['valRet'] - row['expected_retention']) >= Decimal('0.01'):
            issues.warning(document, f'El impuesto retenido en nómina (${row["valRet"]}) no coincide con el calculado (${row["expected_retention"]}). Se declara lo retenido; la diferencia la regulariza el empleado en su declaración.')
        if row['impRentEmpl'] > row['valImpAsuEsteEmpl']:
            issues.error(document, 'El impuesto asumido por la empresa no puede ser mayor al valor del impuesto asumido por este empleador.')
        if manual_item is None and row['basImp'] > 0:
            issues.info(document, 'Sin datos anuales (gastos personales, otros empleadores): se declaran en cero. Regístralos con el botón "Datos anuales".')
        employees.append({'person': person, 'row': row})
        table.append({
            'id': employee.pk, 'name': employee.get_full_name(), 'income': float(row['ingGravConEsteEmpl'] + row['intGrabGen']),
            'iess': float(row['apoPerIess'] + row['aporPerIessConOtrosEmpls']), 'base': float(row['basImp']), 'caused': float(row['impRentCaus']),
            'rebate': float(row['rebajaGastosPersonales']), 'after': float(row['impuestoRentaRebajaGastosPersonales']),
            'withheld': float(row['valRet']), 'manual': manual_item is not None,
        })
    for name, total in unmapped.items():
        issues.warning('Rubros', f'El rubro "{name}" (total ${money(total)}) no está asignado a una casilla del RDEP y NO se incluye. Asígnalo en Recursos Humanos > Rubros.')
    without_payroll = Employee.objects.exclude(pk__in=with_payroll).count()
    if without_payroll:
        issues.info('Empleados', f'{without_payroll} empleado(s) sin nómina en {year} no se incluyen.')
    if not employees:
        issues.info('RDEP', f'No hay empleados con nómina en {year}: el anexo se presenta EN CERO (el SRI lo exige aunque no haya empleados).')
    header = {'ruc': company.ruc, 'year': year, 'employer_type': params.employer_type, 'social_security': params.social_security}
    data = render_xml(header, employees)
    xsd_errors = validate_xml(data)
    summary = {
        'year': year, 'file': f'RDEP{year}.zip', 'employees': table, 'count': len(employees),
        'issues': issues.items, 'errors': sum(1 for i in issues.items if i['level'] == 'error'),
        'warnings': sum(1 for i in issues.items if i['level'] == 'warning'),
        'xsd_errors': xsd_errors, 'valid': not xsd_errors and not issues.has_errors,
        'totals': {k: float(sum((item['row'][k] for item in employees), ZERO)) for k in ('ingGravConEsteEmpl', 'basImp', 'impRentCaus', 'valRet')},
    }
    return data, summary
