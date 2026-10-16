"""Lectura de los archivos de contribuyentes que publica el SRI (uno por provincia, separados por `|`, una fila por
ESTABLECIMIENTO con el texto largo de la actividad económica repetido) y reducción a un archivo ligero con UNA fila por
RUC y solo lo que el sistema usa. Ese archivo se carga con `import_sri_catalog`."""
import csv
import gzip
import io
import os
import zipfile

csv.field_size_limit(10 * 1024 * 1024)

# Columnas del archivo original que se usan.
SOURCE_COLUMNS = ('NUMERO_RUC', 'RAZON_SOCIAL', 'ESTADO_CONTRIBUYENTE', 'TIPO_CONTRIBUYENTE', 'OBLIGADO',
                  'NUMERO_ESTABLECIMIENTO', 'NOMBRE_FANTASIA_COMERCIAL', 'DESCRIPCION_PROVINCIA_EST', 'DESCRIPCION_CANTON_EST')
# Estados válidos: una fila cuyo nombre trae el separador `|` queda con las columnas corridas y se descarta.
VALID_STATUS = ('ACTIVO', 'SUSPENDIDO', 'PASIVO')
# Orden de las columnas del archivo reducido (es el orden que espera `import_sri_catalog`).
SLIM_COLUMNS = ('ruc', 'business_name', 'trade_name', 'status', 'taxpayer_type', 'accounting_required', 'province', 'canton', 'establishment')


def clean(value):
    """Texto seguro para el formato COPY de PostgreSQL (separador `|`, sin barras invertidas ni saltos de línea)."""
    value = (value or '').strip()
    for bad in ('|', '\\', '"', '\r', '\n', '\t'):
        value = value.replace(bad, ' ')
    return ' '.join(value.split())


def open_sources(path):
    """Devuelve (nombre, archivo de texto) por cada CSV encontrado en una carpeta, en un .zip o en un .csv suelto."""
    if os.path.isdir(path):
        for name in sorted(os.listdir(path)):
            yield from open_sources(os.path.join(path, name))
    elif path.lower().endswith('.zip'):
        with zipfile.ZipFile(path) as zf:
            for member in sorted(zf.namelist()):
                if member.lower().endswith('.csv'):
                    with zf.open(member) as raw:
                        yield member, io.TextIOWrapper(raw, encoding='utf-8-sig', errors='replace', newline='')
    elif path.lower().endswith('.csv'):
        with open(path, encoding='utf-8-sig', errors='replace', newline='') as f:
            yield os.path.basename(path), f


def slim_rows(stream):
    """Filas reducidas de un CSV del SRI. Salta las filas repetidas del mismo RUC que vienen seguidas (otros
    establecimientos); si el mismo RUC reaparece más lejos (otra provincia), la base se queda con el establecimiento de
    número más bajo."""
    reader = csv.reader(stream, delimiter='|', quoting=csv.QUOTE_NONE)
    header = next(reader, None)
    if not header:
        return
    index = {name.strip().upper(): i for i, name in enumerate(header)}
    missing = [c for c in SOURCE_COLUMNS if c not in index]
    if missing:
        raise ValueError('Al archivo le faltan las columnas: ' + ', '.join(missing))
    pos = [index[c] for c in SOURCE_COLUMNS]
    last = None
    for row in reader:
        if len(row) <= max(pos):
            continue
        ruc, name, status, kind, required, establishment, trade, province, canton = (clean(row[i]) for i in pos)
        if not ruc.isdigit() or len(ruc) != 13 or not name or ruc == last or status.upper() not in VALID_STATUS:
            continue
        last = ruc
        yield [ruc, name, trade, status.upper(), kind.upper(), 'S' if required.upper() == 'S' else 'N', province.upper(), canton.upper(), establishment]


def build_slim_file(source, out_path, progress=None):
    """Lee todos los CSV de `source` y escribe `out_path` (gzip). Devuelve (filas leídas, archivos procesados)."""
    rows, files = 0, 0
    with gzip.open(out_path, 'wt', encoding='utf-8', newline='') as out:
        for name, stream in open_sources(source):
            files += 1
            for row in slim_rows(stream):
                out.write('|'.join(row) + '\n')
                rows += 1
            if progress:
                progress(name, rows)
    return rows, files
