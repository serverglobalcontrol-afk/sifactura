"""Conciliación bancaria: cruza el estado de cuenta del banco con el libro de
esa cuenta bancaria.

Parte 1 (sin base de datos, se puede probar sola): leer el estado de cuenta en
Excel, CSV o PDF y convertirlo en movimientos {fecha, descripción, referencia,
valor con signo, saldo}.  Positivo = depósito/crédito, negativo = retiro/débito.

Parte 2 (con base de datos): emparejar movimientos del banco con líneas del
libro, y el resumen de conciliación (saldo del banco ajustado vs saldo del
libro ajustado).
"""
import csv
import io
import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

ZERO = Decimal('0.00')
CENT = Decimal('0.01')
MATCH_WINDOW_DAYS = 5

HEADERS = {
    'date': ['fecha', 'fecha contable', 'fecha de transaccion', 'fecha transaccion', 'fecha valor', 'fecha de movimiento', 'fecha movimiento', 'date'],
    'description': ['descripcion', 'detalle', 'concepto', 'transaccion', 'movimiento', 'glosa', 'observacion', 'observaciones', 'description'],
    'reference': ['referencia', 'documento', 'numero documento', 'no documento', 'nro documento', 'num documento', 'numero de documento',
                  'comprobante', 'no comprobante', 'secuencial', 'reference', 'nro comprobante', 'numero comprobante'],
    'debit': ['debito', 'debitos', 'retiro', 'retiros', 'cargo', 'cargos', 'egreso', 'egresos', 'debe', 'withdrawal', 'valor debito'],
    'credit': ['credito', 'creditos', 'deposito', 'depositos', 'abono', 'abonos', 'ingreso', 'ingresos', 'haber', 'deposit', 'valor credito'],
    'amount': ['valor', 'monto', 'importe', 'amount', 'valor total'],
    'type': ['tipo', 'tipo de movimiento', 'tipo movimiento', 'd/c', 'dc', 'naturaleza', 'signo', 'tipo transaccion'],
    'balance': ['saldo', 'saldo contable', 'saldo disponible', 'balance', 'saldo final'],
}

POSITIVE_WORDS = ('deposito', 'abono', 'credito', 'acreditacion', 'recibid', 'interes', 'ingreso', 'devolucion', 'transferencia recib')
NEGATIVE_WORDS = ('debito', 'retiro', 'cargo', 'comision', 'cheque', 'pago', 'impuesto', 'iva', 'mantenimiento', 'servicio', 'compra',
                  'transferencia env', 'transferencia a', 'nota de debito', 'nd ', 'isd')

DATE_FORMATS = ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%y', '%Y/%m/%d', '%d.%m.%Y', '%d-%m-%y')
MONTHS_ES = {'ene': 1, 'feb': 2, 'mar': 3, 'abr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'ago': 8, 'sep': 9, 'set': 9, 'oct': 10, 'nov': 11, 'dic': 12}
# "11-ago." / "02 sep" / "5-oct-2026": fecha con el mes en letras (muchos PDF de bancos omiten el año).
NAMED_DATE_AT_START = re.compile(r'^\s*(\d{1,2})[-/ ]([A-Za-z]{3})\.?(?:[-/](\d{2}|\d{4})|\s(\d{4}))?(?=\s|$)')
DATE_AT_START = re.compile(r'^\s*(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{4}[/\-]\d{1,2}[/\-]\d{1,2})')
MONEY_TOKEN = re.compile(r'(?<![\w.,])-?\(?\$?\s?\d{1,3}(?:[.,]\d{3})*[.,]\d{2}\)?(?![\w])|(?<![\w.,])-?\(?\$?\s?\d+[.,]\d{2}\)?(?![\w])')


class StatementError(ValueError):
    """El archivo no se pudo leer; el mensaje dice qué hacer."""


# ------------------------------------------------------------------ utilidades
def normalize(text):
    text = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode('ascii').lower()
    text = re.sub(r'[^a-z0-9/ ]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def parse_date(value):
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and 30000 < value < 80000:
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
    text = str(value).strip()
    match = DATE_AT_START.match(text)
    if not match:
        return None
    text = match.group(1)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_money(value):
    """'1.234,56' / '1,234.56' / '(25.00)' / '-$ 3.10' -> Decimal; None si no es un valor."""
    if value is None or value == '':
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(CENT)
    text = str(value).strip().replace('\xa0', ' ')
    if not text or text in ('-', '--'):
        return None
    negative = text.startswith('(') and text.endswith(')') or text.startswith('-') or text.endswith('-')
    text = re.sub(r'[^0-9.,]', '', text)
    if not text or not re.search(r'\d', text):
        return None
    if ',' in text and '.' in text:
        decimal_sep = ',' if text.rfind(',') > text.rfind('.') else '.'
        thousand_sep = '.' if decimal_sep == ',' else ','
        text = text.replace(thousand_sep, '').replace(decimal_sep, '.')
    elif ',' in text:
        if re.fullmatch(r'\d{1,3}(,\d{3})+', text):
            text = text.replace(',', '')
        else:
            text = text.replace(',', '.')
    elif text.count('.') > 1:
        text = text.replace('.', '')
    try:
        amount = Decimal(text).quantize(CENT)
    except InvalidOperation:
        return None
    return -amount if negative else amount


def _field_of(header):
    h = normalize(header)
    if not h:
        return None
    for field, aliases in HEADERS.items():
        if h in aliases:
            return field
    for field, aliases in HEADERS.items():
        if any(h.startswith(a + ' ') for a in aliases):
            return field
    return None


def _sign_from_type(text):
    t = normalize(text)
    if not t:
        return None
    if t[0] == 'd' and not t.startswith('dep') or 'debit' in t or 'retiro' in t or 'cargo' in t:
        return -1
    if t[0] == 'c' or 'credit' in t or 'deposit' in t or 'abono' in t:
        return 1
    return None


def guess_sign(description):
    """Signo de un movimiento por su descripción (cuando el archivo no dice la columna)."""
    d = normalize(description)
    if any(w in d for w in POSITIVE_WORDS):
        return 1
    if any(w in d for w in NEGATIVE_WORDS):
        return -1
    return None


# ------------------------------------------------------------- Excel y CSV
def _table_to_rows(table):
    """`table`: lista de filas (listas de celdas). Devuelve (movimientos, avisos)."""
    header_index, columns = None, {}
    for index, row in enumerate(table[:40]):
        found = {}
        for col, cell in enumerate(row):
            field = _field_of(cell)
            if field and field not in found:
                found[field] = col
        if 'date' in found and ('amount' in found or 'debit' in found or 'credit' in found):
            header_index, columns = index, found
            break
    if header_index is None:
        raise StatementError(
            'No encontré las columnas del estado de cuenta. El archivo debe tener una fila de títulos con al menos: '
            'Fecha y (Débito y Crédito) o Valor. Opcionales: Descripción/Detalle, Referencia/Documento, Saldo. '
            'Revisa que el Excel/CSV sea el estado de cuenta y que no tenga las columnas en otra hoja.')
    rows, warnings, skipped = [], [], 0
    for line_no, row in enumerate(table[header_index + 1:], start=header_index + 2):
        def cell(field):
            col = columns.get(field)
            return row[col] if col is not None and col < len(row) else None
        movement_date = parse_date(cell('date'))
        if movement_date is None:
            if any(str(c or '').strip() for c in row):
                skipped += 1
            continue
        description = str(cell('description') or '').strip()
        reference = str(cell('reference') or '').strip()
        if reference.endswith('.0') and reference[:-2].isdigit():
            reference = reference[:-2]
        amount = None
        if 'debit' in columns or 'credit' in columns:
            debit, credit = parse_money(cell('debit')), parse_money(cell('credit'))
            if credit:
                amount = abs(credit)
            elif debit:
                amount = -abs(debit)
        else:
            amount = parse_money(cell('amount'))
            if amount is not None and 'type' in columns:
                sign = _sign_from_type(cell('type'))
                if sign is not None:
                    amount = abs(amount) * sign
        if amount is None or amount == 0:
            skipped += 1
            continue
        rows.append({'date': movement_date, 'description': description[:300], 'reference': reference[:60], 'amount': amount, 'balance': parse_money(cell('balance'))})
    if skipped:
        warnings.append(f'Se omitieron {skipped} fila(s) sin fecha o sin valor (totales, títulos o líneas vacías).')
    return rows, warnings


def _read_csv(data):
    for encoding in ('utf-8-sig', 'latin-1'):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ';' if sample.count(';') > sample.count(',') else ','
    return [row for row in csv.reader(io.StringIO(text), dialect)]


def _read_excel(data):
    from openpyxl import load_workbook
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise StatementError('No pude abrir el Excel. Guárdalo como .xlsx (Excel moderno) o como CSV y vuelve a intentar.')
    best = []
    for sheet in workbook.worksheets:
        table = [list(row) for row in sheet.iter_rows(values_only=True)]
        if len(table) > len(best):
            best = table
    return best


# ------------------------------------------------------------------------ PDF
def _pdf_text(data):
    try:
        from PyPDF3 import PdfFileReader
        reader = PdfFileReader(io.BytesIO(data), strict=False)
        if reader.isEncrypted:
            try:
                reader.decrypt('')
            except Exception:
                raise StatementError('El PDF tiene contraseña. Quítala o descarga el estado de cuenta en Excel/CSV.')
        return '\n'.join((reader.getPage(i).extractText() or '') for i in range(reader.getNumPages()))
    except StatementError:
        raise
    except Exception:
        raise StatementError('No pude leer el PDF. Si es una imagen escaneada no sirve: descarga el estado de cuenta del banco en Excel o CSV.')


def _start_date(line, year=None):
    """(fecha, resto de la línea) si la línea EMPIEZA con una fecha, numérica o con el mes en
    letras; si no trae año, se usa `year` o el año actual (sin caer en el futuro)."""
    match = DATE_AT_START.match(line)
    if match and parse_date(match.group(1)):
        return parse_date(match.group(1)), line[match.end():].strip()
    named = NAMED_DATE_AT_START.match(line)
    if named and named.group(2).lower() in MONTHS_ES:
        day, month = int(named.group(1)), MONTHS_ES[named.group(2).lower()]
        explicit = named.group(3) or named.group(4)
        if explicit:
            y = int(explicit)
            y = y + 2000 if y < 100 else y
        else:
            y = int(year) if year else date.today().year
        try:
            result = date(y, month, day)
        except ValueError:
            return None, line
        if not explicit and not year and result > date.today() + timedelta(days=1):
            result = date(y - 1, month, day)
        return result, line[named.end():].strip()
    return None, line


def parse_pdf_text(text, opening_balance=None, year=None):
    """Movimientos desde el TEXTO de un estado de cuenta en PDF.

    Un movimiento empieza en una fecha y llega hasta la siguiente. Un PDF no dice
    si el valor es débito o crédito: el signo se deduce comparando el saldo
    corriente (si el PDF lo trae) y, si no, por palabras de la descripción.
    Siempre se avisa lo deducido para que se revise antes de conciliar."""
    records = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        found, rest = _start_date(line, year)
        if found:
            records.append({'date': found, 'text': rest})
        elif records:
            records[-1]['text'] += ' ' + line
    parsed = []
    for record in records:
        tokens = [m.group(0) for m in MONEY_TOKEN.finditer(record['text'])]
        values = [parse_money(t) for t in tokens]
        values = [v for v in values if v is not None]
        if not values:
            continue
        parsed.append({'date': record['date'], 'text': record['text'], 'tokens': tokens, 'values': values})
    if not parsed:
        raise StatementError('No encontré movimientos en el PDF (fecha + valor). Descarga el estado de cuenta del banco en Excel o CSV, o envíame el PDF para adaptar la lectura.')
    has_balance = sum(1 for p in parsed if len(p['values']) >= 2) >= 0.7 * len(parsed)
    if len(parsed) > 1 and parsed[0]['date'] > parsed[-1]['date']:
        parsed.reverse()
    warnings = ['Estado de cuenta en PDF: el signo de cada movimiento (depósito o retiro) se DEDUCE; revísalos antes de conciliar.']
    rows, previous, guessed = [], Decimal(opening_balance) if opening_balance is not None else None, 0
    for p in parsed:
        balance = p['values'][-1] if has_balance and len(p['values']) >= 2 else None
        if has_balance and len(p['values']) >= 3:
            # Columnas Débito, Crédito y Saldo: una de las dos primeras es 0.00.
            amount = abs(p['values'][-2] - p['values'][-3])
        else:
            amount = abs(p['values'][-2] if has_balance and len(p['values']) >= 2 else p['values'][-1])
        description = MONEY_TOKEN.sub(' ', p['text'])
        reference = ''
        ref_match = re.search(r'(?<![\d.,/-])(\d{5,})(?![\d.,/-])', description)
        if ref_match:
            reference = ref_match.group(1)
            description = description.replace(reference, ' ', 1)
        description = re.sub(r'\s+', ' ', description).strip(' -')
        # Número de oficina u otros códigos cortos que quedaron antes de la descripción.
        description = re.sub(r'^(?:\d{1,3}\s+)+(?=\D)', '', description)
        sign = None
        if balance is not None and previous is not None:
            delta = (balance - previous).quantize(CENT)
            if abs(delta) == amount:
                sign = 1 if delta > 0 else -1
        if sign is None:
            sign = guess_sign(description)
            guessed += 1
        if sign is None:
            sign = 1
        rows.append({'date': p['date'], 'description': description[:300], 'reference': reference[:60], 'amount': amount * sign, 'balance': balance})
        previous = balance if balance is not None else previous
    if guessed:
        warnings.append(f'{guessed} movimiento(s) con el signo deducido por su descripción, no por el saldo: verifica depósitos y retiros.')
    return rows, warnings


# --------------------------------------------------------------------- entrada
def parse_statement_file(data, filename, opening_balance=None, year=None):
    """Lee un estado de cuenta (xlsx, csv o pdf). Devuelve (movimientos, avisos, origen)."""
    name = (filename or '').lower()
    if name.endswith(('.xlsx', '.xlsm')):
        rows, warnings = _table_to_rows(_read_excel(data))
        source = 'excel'
    elif name.endswith('.xls'):
        raise StatementError('El formato .xls (Excel antiguo) no se puede leer. Ábrelo y guárdalo como .xlsx o CSV.')
    elif name.endswith(('.csv', '.txt')):
        rows, warnings = _table_to_rows(_read_csv(data))
        source = 'csv'
    elif name.endswith('.pdf') or data[:4] == b'%PDF':
        rows, warnings = parse_pdf_text(_pdf_text(data), opening_balance, year)
        source = 'pdf'
    else:
        raise StatementError('Formato no admitido. Sube el estado de cuenta en Excel (.xlsx), CSV o PDF.')
    if not rows:
        raise StatementError('El archivo no tiene movimientos con fecha y valor.')
    return rows, warnings, source


# ------------------------------------------------------- con base de datos
def book_movement(line):
    """Valor de una línea del libro como lo ve el banco: depósito +, retiro -."""
    return (line.debit - line.credit).quantize(CENT)


def _unmatched_book_lines(bank_account, date_to):
    from core.contabilidad.models import JournalEntryLine
    return list(
        JournalEntryLine.objects.filter(account=bank_account.account, entry__status='posted', entry__date__lte=date_to, bank_match__isnull=True)
        .select_related('entry').order_by('entry__date', 'id'))


def _ref_match(statement_reference, entry_reference):
    a, b = (statement_reference or '').lstrip('0'), (entry_reference or '').lstrip('0')
    return bool(a and b and (a == b or a in b or b in a))


def auto_match(statement, window_days=MATCH_WINDOW_DAYS):
    """Empareja por mismo valor y fecha cercana (±window_days); prefiere el mismo
    número de comprobante. Uno a uno. Devuelve la cantidad conciliada."""
    from django.utils import timezone
    pool = _unmatched_book_lines(statement.bank_account, statement.date_to + timedelta(days=window_days))
    matched = 0
    for line in statement.lines.filter(entry_line__isnull=True, is_opening=False).order_by('date', 'id'):
        best, best_score = None, None
        for candidate in pool:
            if book_movement(candidate) != line.amount:
                continue
            days = abs((candidate.entry.date - line.date).days)
            if days > window_days:
                continue
            score = (0 if _ref_match(line.reference, candidate.entry.reference) else 1, days)
            if best is None or score < best_score:
                best, best_score = candidate, score
        if best is not None:
            line.entry_line, line.matched_at = best, timezone.now()
            line.save(update_fields=['entry_line', 'matched_at'])
            pool.remove(best)
            matched += 1
    return matched


def book_balance_before(bank_account, day):
    from django.db.models import Sum
    from core.contabilidad.models import JournalEntryLine
    total = JournalEntryLine.objects.filter(account=bank_account.account, entry__status='posted', entry__date__lt=day).aggregate(d=Sum('debit'), c=Sum('credit'))
    return (total['d'] or ZERO) - (total['c'] or ZERO)


def mark_opening(statement):
    """Da por conciliados los asientos de esta cuenta ANTERIORES al estado de cuenta:
    el banco ya los tenía en su saldo inicial. Devuelve cuántos."""
    from django.utils import timezone
    from core.contabilidad.models import BankStatementLine
    if statement.status == 'reconciled':
        raise ValueError('La conciliación ya está cerrada: reábrela para cambiar emparejamientos.')
    count = 0
    for line in _unmatched_book_lines(statement.bank_account, statement.date_from - timedelta(days=1)):
        BankStatementLine.objects.create(
            statement=statement, date=line.entry.date, description='Asiento anterior al estado de cuenta (ya conciliado en el saldo inicial)',
            reference=line.entry.reference, amount=book_movement(line), entry_line=line, matched_at=timezone.now(), is_opening=True)
        count += 1
    return count


def clear_opening(statement):
    if statement.status == 'reconciled':
        raise ValueError('La conciliación ya está cerrada: reábrela para cambiar emparejamientos.')
    return statement.lines.filter(is_opening=True).delete()[0]


def manual_match(statement_line, journal_line):
    from django.utils import timezone
    statement = statement_line.statement
    if statement.status == 'reconciled':
        raise ValueError('La conciliación ya está cerrada: reábrela para cambiar emparejamientos.')
    if journal_line.account_id != statement.bank_account.account_id:
        raise ValueError('Esa línea del libro no pertenece a esta cuenta bancaria.')
    if getattr(journal_line, 'bank_match', None) is not None:
        raise ValueError('Esa línea del libro ya está conciliada con otro movimiento del banco.')
    if book_movement(journal_line) != statement_line.amount:
        raise ValueError(f'Los valores no coinciden: banco {statement_line.amount} y libro {book_movement(journal_line)}. Para una diferencia, corrige el asiento o regístra el movimiento que falta.')
    statement_line.entry_line, statement_line.matched_at = journal_line, timezone.now()
    statement_line.save(update_fields=['entry_line', 'matched_at'])


def unmatch(statement_line):
    if statement_line.statement.status == 'reconciled':
        raise ValueError('La conciliación ya está cerrada: reábrela para cambiar emparejamientos.')
    statement_line.entry_line, statement_line.matched_at = None, None
    statement_line.save(update_fields=['entry_line', 'matched_at'])


def post_statement_line(statement_line, counter_account, user=None):
    """Registra en el libro un movimiento que el banco tiene y la empresa no
    (comisión, interés, depósito sin registrar...) y lo concilia."""
    from core.contabilidad.services import posting
    statement = statement_line.statement
    if statement.status == 'reconciled':
        raise ValueError('La conciliación ya está cerrada: reábrela para registrar movimientos.')
    if statement_line.entry_line_id:
        raise ValueError('Este movimiento ya está conciliado.')
    bank = statement.bank_account
    amount = abs(statement_line.amount)
    if statement_line.amount > 0:
        lines = [posting.Line(bank.account, debit=amount, bank_account=bank), posting.Line(counter_account, credit=amount)]
    else:
        lines = [posting.Line(bank.account, credit=amount, bank_account=bank), posting.Line(counter_account, debit=amount)]
    description = f'Conciliación bancaria: {statement_line.description or "movimiento del banco"}'
    entry = posting.create_manual_entry(statement_line.date, description, lines, source_type='bank_move', user=user, reference=statement_line.reference)
    journal_line = entry.lines.filter(account=bank.account).first()
    manual_match(statement_line, journal_line)
    return entry


FEE_WORDS = ('comision', 'iva cobrado', 'mantenimiento', 'cargo por', 'impuesto', 'isd', 'sobregiro')


def post_opening(statement, counter_account, user=None):
    """Registra en el libro el saldo con el que el banco empezó el período (cuando la
    empresa no lo tenía registrado) y lo da por conciliado."""
    from core.contabilidad.services import posting
    if statement.status == 'reconciled':
        raise ValueError('La conciliación ya está cerrada: reábrela para registrar movimientos.')
    amount = statement.opening_balance
    if amount is None or amount == 0:
        raise ValueError('Este estado de cuenta no tiene saldo inicial (o es 0): no hay nada que registrar.')
    bank = statement.bank_account
    if book_balance_before(bank, statement.date_from) == amount:
        raise ValueError('El libro ya tiene ese saldo inicial: usa "Marcar anteriores como conciliados".')
    gap = amount - book_balance_before(bank, statement.date_from)
    day = statement.date_from - timedelta(days=1)
    if gap > 0:
        lines = [posting.Line(bank.account, debit=gap, bank_account=bank), posting.Line(counter_account, credit=gap)]
    else:
        lines = [posting.Line(bank.account, credit=-gap, bank_account=bank), posting.Line(counter_account, debit=-gap)]
    posting.create_manual_entry(day, 'Saldo inicial de la cuenta bancaria según el banco', lines, source_type='bank_move', user=user, reference='SALDO INICIAL')
    return mark_opening(statement)


def post_pending(statement, income_account, expense_account, fee_account, user=None):
    """Registra TODOS los movimientos del banco sin conciliar: comisiones e impuestos van a la
    cuenta de gastos bancarios, los demás cobros a `income_account` y los demás pagos a
    `expense_account`. Es lo mismo que el botón "+" de cada fila, de una sola vez."""
    count = 0
    for line in statement.lines.filter(entry_line__isnull=True, is_opening=False).order_by('date', 'id'):
        description = normalize(line.description)
        if line.amount < 0 and any(word in description for word in FEE_WORDS):
            account = fee_account
        elif line.amount > 0:
            account = income_account
        else:
            account = expense_account
        post_statement_line(line, account, user)
        count += 1
    return count


def summary(statement):
    """Saldo del banco vs saldo del libro, con las partidas conciliatorias."""
    from django.db.models import Sum
    from core.contabilidad.models import JournalEntryLine
    bank = statement.bank_account
    book = JournalEntryLine.objects.filter(account=bank.account, entry__status='posted', entry__date__lte=statement.date_to).aggregate(d=Sum('debit'), c=Sum('credit'))
    book_balance = (book['d'] or ZERO) - (book['c'] or ZERO)
    book_pending = _unmatched_book_lines(bank, statement.date_to)
    book_pending_total = sum((book_movement(l) for l in book_pending), ZERO)
    bank_pending_total = sum((l.amount for l in statement.lines.filter(entry_line__isnull=True, is_opening=False)), ZERO)
    bank_closing = statement.closing_balance
    # Banco ajustado: lo que el banco todavía no refleja (depósitos en tránsito -, cheques/pagos no cobrados).
    adjusted_bank = bank_closing + book_pending_total
    # Libro ajustado: lo que el banco ya hizo y la empresa no ha registrado.
    adjusted_book = book_balance + bank_pending_total
    difference = (adjusted_bank - adjusted_book).quantize(CENT)
    return {
        'bank_closing': float(bank_closing), 'book_balance': float(book_balance),
        'book_pending_total': float(book_pending_total), 'book_pending_count': len(book_pending),
        'bank_pending_total': float(bank_pending_total), 'bank_pending_count': statement.lines.filter(entry_line__isnull=True, is_opening=False).count(),
        'opening_marked': statement.lines.filter(is_opening=True).count(),
        'book_before_start': float(book_balance_before(bank, statement.date_from)), 'opening_balance': float(statement.opening_balance) if statement.opening_balance is not None else None,
        'adjusted_bank': float(adjusted_bank), 'adjusted_book': float(adjusted_book),
        'difference': float(difference), 'balanced': difference == 0,
    }
