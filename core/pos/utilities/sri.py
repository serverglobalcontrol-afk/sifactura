import base64
import logging
import os.path
import random
import smtplib
import string
import subprocess
import uuid
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from itertools import cycle
from pathlib import Path
from tempfile import NamedTemporaryFile

import requests
from django.core.files import File
from lxml import etree
from suds.client import Client

from config import settings
from core.pos.choices import VOUCHER_STAGE, INVOICE_STATUS

logger = logging.getLogger('invoicepro')


def signature_validity(p12_bytes, password):
    """(inicio, fin) de vigencia del certificado de firma electrónica (.p12),
    como datetimes con zona UTC; None si no se puede leer (clave incorrecta o
    archivo dañado: en ese caso es la propia firma la que lo informa)."""
    from cryptography.hazmat.primitives.serialization import pkcs12
    try:
        _, certificate, _ = pkcs12.load_key_and_certificates(p12_bytes, (password or '').encode())
    except Exception:
        return None
    if certificate is None:
        return None
    start = getattr(certificate, 'not_valid_before_utc', None) or certificate.not_valid_before.replace(tzinfo=timezone.utc)
    end = getattr(certificate, 'not_valid_after_utc', None) or certificate.not_valid_after.replace(tzinfo=timezone.utc)
    return start, end


def signature_validity_problem(p12_bytes, password, now=None):
    """None si el certificado está vigente; si no, un mensaje claro. El SRI
    rechaza con "FIRMA INVALIDA" cualquier comprobante firmado fuera de la
    vigencia del certificado, y el número del comprobante ya se consumió: por
    eso se revisa ANTES de firmar y enviar."""
    validity = signature_validity(p12_bytes, password)
    if validity is None:
        return None
    start, end = validity
    now = now or datetime.now(timezone.utc)
    if now > end:
        return (f'El certificado de firma electrónica de la empresa VENCIÓ el {end.astimezone().strftime("%d/%m/%Y")}. '
                'El SRI rechaza todo comprobante firmado con un certificado vencido. Carga un certificado vigente en '
                'Editar Compañía > Firma electrónica y vuelve a intentar.')
    if now < start:
        return (f'El certificado de firma electrónica de la empresa todavía no está vigente: empieza el {start.astimezone().strftime("%d/%m/%Y %H:%M")}. '
                'Verifica que la fecha y hora del servidor sean correctas, o espera a que inicie su vigencia.')
    return None


def describe_sri_rejection(items):
    """Mensaje claro para el usuario a partir de la lista de mensajes con que el
    SRI devuelve o no autoriza un comprobante ([{identificador, mensaje,
    informacionAdicional, tipo}]). El detalle original se conserva aparte."""
    parts = []
    for item in items or []:
        identifier = str(item.get('identificador', '')).strip()
        message = str(item.get('mensaje', '')).strip()
        extra = str(item.get('informacionAdicional', '')).strip()
        low = f'{message} {extra}'.lower()
        if identifier == '39' or 'firma invalida' in low or 'firma inválida' in low:
            if 'periodo de validez' in low or 'período de validez' in low:
                parts.append('La firma electrónica de la empresa está VENCIDA o todavía no es vigente para la fecha del comprobante. '
                             'Carga un certificado vigente en Editar Compañía > Firma electrónica y vuelve a generar el comprobante.')
            else:
                parts.append(f'El SRI rechazó la firma electrónica ({extra or message}). Verifica que el certificado cargado '
                             'pertenezca al RUC de la empresa y que su clave sea la correcta.')
        elif identifier == '52' or 'error en diferencias' in low:
            parts.append(_explain_differences(extra or message))
        else:
            code = f' (código {identifier})' if identifier else ''
            parts.append(f'{message}{": " + extra if extra else ""}{code}'.strip())
    return ' '.join(p for p in parts if p)


def _explain_differences(detail):
    """El SRI devuelve "ERROR EN DIFERENCIAS" con una lista de cosas que no
    cuadran. Se explica en palabras simples y se deja lo que dijo el SRI."""
    import re
    cleaned = re.sub(r'-+\s*inventario de errores\s*-+', '\n', str(detail), flags=re.I)
    lines = [l.strip(' -') for l in cleaned.splitlines() if l.strip(' -')]
    if not lines:
        lines = [str(detail).strip()]
    simple = []
    for line in lines:
        low = line.lower()
        if 'tipo de sujeto retenido' in low and 'exterior' in low:
            simple.append('Se estaba enviando el dato "tipo de sujeto retenido" (persona natural o sociedad), '
                          'pero el SRI solo lo acepta cuando el proveedor es del exterior. Es un detalle del sistema, no tuyo.')
        else:
            simple.append(line)
    return ('El SRI devolvió el comprobante porque encontró datos que no coinciden o que no corresponden. '
            'Esto es lo que dijo el SRI: ' + ' | '.join(simple) + '. Si no logras corregirlo, envía este mensaje a soporte.')


def error_text(error, default=None):
    """Texto legible de lo que devuelve una emisión en result['error']: ya sea un
    mensaje (str) o el rechazo del SRI (dict con 'message')."""
    if isinstance(error, str) and error:
        return error
    if isinstance(error, dict) and error.get('message'):
        return error['message']
    return default


def describe_sri_error(exc):
    """Convierte un error técnico de conexión con el SRI en un mensaje que el
    usuario entienda y que le diga qué hacer. El error original sigue en el log
    (logger.exception) y se conserva al final del mensaje para soporte."""
    text = str(exc)
    low = text.lower()
    if 'timed out' in low or 'timeout' in low:
        return ('El SRI no respondió a tiempo: su servicio está lento o no es accesible desde el servidor. '
                'El comprobante quedó guardado como "Sin Autorizar" y NO se perdió: reintenta en unos minutos '
                f'desde el listado ("Generar ... pendientes"). Detalle técnico: {text}')
    if any(token in low for token in ('connection refused', 'connection reset', 'name or service not known',
                                      'temporary failure in name resolution', 'network is unreachable',
                                      'no route to host', 'max retries exceeded', 'ssl', 'urlopen error')):
        return ('No se pudo conectar con el servicio del SRI desde el servidor. '
                'El comprobante quedó guardado como "Sin Autorizar" y NO se perdió: reintenta en unos minutos '
                f'desde el listado. Detalle técnico: {text}')
    return text


class SRI:
    def __init__(self):
        self.current_date = datetime.now()
        self.base_dir = os.path.dirname(__file__)

    def get_absolute_path(self, path):
        return str(Path(path).absolute())

    def compute_mod11(self, pass_key_48=''):
        if len(pass_key_48) > 48:
            return ''
        addition = 0
        factors = cycle((2, 3, 4, 5, 6, 7))
        for digit, factor in zip(reversed(pass_key_48), factors):
            addition += int(digit) * factor
        number = 11 - addition % 11
        if number == 11:
            number = 0
        elif number == 10:
            number = 1
        return str(number)

    def generate_number(self, amount=8):
        return ''.join(random.choices(list(string.digits), k=amount))

    def create_access_key(self, instance):
        password_48 = f"{datetime.now().strftime('%d%m%Y')}{instance.receipt.voucher_type}{instance.company.ruc}{instance.company.environment_type}{instance.receipt.establishment_code}{instance.receipt.issuing_point_code}{instance.voucher_number}{self.generate_number()}{instance.company.emission_type}"
        module11 = self.compute_mod11(pass_key_48=password_48)
        if len(module11):
            return f'{password_48}{module11}'
        return None

    def get_receipt_url(self, instance):
        if instance.company.environment_type == 2:
            return 'https://cel.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline?wsdl'
        return 'https://celcer.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline?wsdl'

    def get_authorization_url(self, instance):
        if instance.company.environment_type == 2:
            return 'https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl'
        return 'https://celcer.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl'

    def check_sequential_error(self, errors):
        if 'error' in errors and isinstance(errors['error'], dict):
            if 'errors' in errors['error']:
                for error in errors['error']['errors']:
                    if 'mensaje' in error and error['mensaje'] == 'ERROR SECUENCIAL REGISTRADO':
                        return True
        return False

    def create_voucher_errors(self, instance, errors):
        from core.pos.models import VoucherErrors
        try:
            voucher_errors = VoucherErrors()
            voucher_errors.reference = instance.voucher_number_full
            voucher_errors.stage = errors['stage']
            voucher_errors.receipt = instance.receipt
            if type(errors) is str:
                voucher_errors.errors = {'error': errors}
            else:
                voucher_errors.errors = errors
            voucher_errors.environment_type = instance.environment_type
            voucher_errors.save()
        except:
            pass
        finally:
            if self.check_sequential_error(errors=errors):
                instance.status = INVOICE_STATUS[4][0]
                instance.edit()
                instance.receipt.sequence = instance.receipt.sequence + 1
                instance.receipt.save()

    def create_xml(self, instance):
        response = {'resp': False, 'stage': VOUCHER_STAGE[1][0]}
        try:
            xml, access_code = instance.generate_xml()
            instance.access_code = access_code
            instance.save()
            response['resp'] = True
            response['xml'] = xml
        except Exception as e:
            response['error'] = str(e)
        finally:
            if 'error' in response:
                self.create_voucher_errors(instance, response)
        return response

    def firm_xml(self, instance, xml):
        response = {'resp': False, 'stage': VOUCHER_STAGE[1][0]}
        file_temp_name = ''
        try:
            with NamedTemporaryFile(suffix='.xml', delete=False) as file_temp:
                file_temp.write(xml.encode())
                file_temp.flush()
                file_temp_name = file_temp.name
                jar_path = self.get_absolute_path(os.path.join(os.path.dirname(self.base_dir), 'resources/jar/sri.jar'))
                certificate_path = self.get_absolute_path(f'{settings.BASE_DIR}/{instance.company.get_electronic_signature()}')
                certificate_key = instance.company.electronic_signature_key
                # Certificado vencido o aún no vigente: se informa de inmediato y con
                # claridad, sin firmar ni molestar al SRI (que lo rechazaría igual).
                with open(certificate_path, 'rb') as certificate_file:
                    problem = signature_validity_problem(certificate_file.read(), certificate_key)
                if problem:
                    response['error'] = problem
                    return response
                # Único por documento: dos comprobantes de distinto tipo (o de dos
                # empresas) con el mismo secuencial no deben pisar el mismo archivo.
                xml_name = f'{type(instance).__name__.lower()}_{instance.voucher_number}_{uuid.uuid4().hex[:8]}.xml'
                commands = ['java', '-jar', jar_path, certificate_path, certificate_key, file_temp.name, self.base_dir, xml_name]
                procedure = subprocess.run(args=commands, capture_output=True)
                if procedure.returncode == 0:
                    error = procedure.stdout.decode('utf-8')
                    if error.__contains__('Error'):
                        response['error'] = error
                    else:
                        generated_xml_path = os.path.join(self.base_dir, xml_name)
                        with open(generated_xml_path, 'rb') as file:
                            response['resp'] = True
                            response['xml'] = file.read().decode('utf-8')
                        if os.path.exists(generated_xml_path):
                            os.remove(generated_xml_path)
                else:
                    response['error'] = procedure.stderr.decode('utf-8')
        except Exception as e:
            response['error'] = str(e)
        finally:
            if os.path.exists(file_temp_name):
                os.remove(file_temp_name)
            if 'error' in response:
                self.create_voucher_errors(instance, response)
        return response

    def has_sequential_error(self, errors):
        try:
            for error in errors.get('error', {}).get('errors', []):
                if error.get('mensaje') == 'ERROR SECUENCIAL REGISTRADO':
                    return True
        except (AttributeError, TypeError):
            pass
        return False

    def validate_xml(self, instance, xml):
        response = {'resp': False, 'stage': VOUCHER_STAGE[2][0]}
        try:
            document = xml.strip().encode('utf-8')
            base64_binary_xml = base64.b64encode(document).decode('utf-8')
            # timeout=30: suds trae un valor por defecto de 90s si no se
            # especifica, pero mejor explícito y más corto -si el SRI se
            # pone lento, la petición falla rápido y libera el worker de
            # gunicorn en vez de tenerlo ocupado por más tiempo del
            # necesario (con pocos workers totales, varias facturaciones
            # lentas a la vez podrían saturar el sistema para todos).
            sri_client = Client(self.get_receipt_url(instance), timeout=30)
            result = sri_client.service.validarComprobante(base64_binary_xml)
            status = result.estado
            if status == 'DEVUELTA':
                receipt = result.comprobantes.comprobante[0]
                response['error'] = {'access_code': receipt.claveAcceso, 'errors': []}
                for count, value in enumerate(receipt.mensajes):
                    message = value[1][count]
                    values = dict()
                    for name in ['identificador', 'informacionAdicional', 'mensaje', 'tipo']:
                        if name in message:
                            values[name] = message[name]
                    response['error']['errors'].append(values)
                response['error']['message'] = describe_sri_rejection(response['error']['errors'])
            elif status == 'RECIBIDA':
                response['resp'] = True
                response['xml'] = xml
        except Exception as e:
            response['error'] = describe_sri_error(e)
            logger.exception('SRI validate_xml falló para %s', getattr(instance, 'voucher_number_full', instance.pk))
        finally:
            if not response.get('resp') and self.has_sequential_error(response):
                response = {'resp': True, 'xml': xml}
            elif 'error' in response:
                self.create_voucher_errors(instance, response)

        return response

    def authorize_xml(self, instance):
        response = {'resp': False, 'stage': VOUCHER_STAGE[3][0]}
        try:
            sri_client = Client(self.get_authorization_url(instance), timeout=30)
            result = sri_client.service.autorizacionComprobante(instance.access_code)
            if len(result):
                # Mientras el SRI todavía está procesando el comprobante, el
                # nodo <autorizaciones> viene vacío y la librería SOAP lo
                # interpreta como texto plano en vez de un objeto con
                # atributos, sin autorizaciones aún. No es un error: hay que
                # reintentar más tarde (el llamador ya reintenta 3 veces).
                autorizaciones = getattr(result[2], 'autorizacion', None)
                if not autorizaciones:
                    return response
                receipt = autorizaciones[0]
                if receipt.estado == 'NO AUTORIZADO':
                    response['error'] = {'access_code': instance.access_code, 'stage': receipt.estado, 'authorization_date': str(receipt.fechaAutorizacion), 'errors': []}
                    for count, value in enumerate(receipt.mensajes):
                        message = value[1][count]
                        values = dict()
                        for name in ['identificador', 'informacionAdicional', 'mensaje', 'tipo']:
                            if name in message:
                                values[name] = message[name]
                        response['error']['errors'].append(values)
                    response['error']['message'] = describe_sri_rejection(response['error']['errors'])
                else:
                    xml_authorization = etree.Element('autorizacion')
                    etree.SubElement(xml_authorization, 'estado').text = receipt.estado
                    etree.SubElement(xml_authorization, 'numeroAutorizacion').text = receipt.numeroAutorizacion
                    etree.SubElement(xml_authorization, 'fechaAutorizacion', attrib={'class': "fechaAutorizacion"}).text = str(receipt.fechaAutorizacion.strftime("%d/%m/%Y %H:%M:%S"))
                    voucher_sri = etree.SubElement(xml_authorization, 'comprobante')
                    voucher_sri.text = etree.CDATA(receipt.comprobante)
                    xml_text = etree.tostring(xml_authorization, encoding="utf8", xml_declaration=True).decode('utf8').replace("'", '"')
                    with NamedTemporaryFile(delete=True) as file_temp:
                        xml_path = f'{instance.company.scheme.schema_name}/xml/{self.current_date.year}/{self.current_date.month}/{self.current_date.day}/{instance.receipt.get_name_xml()}_{instance.access_code}.xml'
                        file_temp.write(xml_text.encode())
                        file_temp.flush()
                        instance.xml_authorized.save(name=xml_path, content=File(file_temp))
                        instance.authorization_date = receipt.fechaAutorizacion
                        instance.generate_pdf_authorized()
                        instance.status = INVOICE_STATUS[1][0]
                        instance.save()
                        response['resp'] = True
        except Exception as e:
            response['error'] = describe_sri_error(e)
            logger.exception('SRI authorize_xml falló para %s', getattr(instance, 'voucher_number_full', instance.pk))
        finally:
            if 'error' in response:
                self.create_voucher_errors(instance, response)
        return response

    def notify_by_email(self, instance, company, client):
        response = {'resp': False, 'stage': VOUCHER_STAGE[4][0]}
        try:
            if client.send_email_invoice:
                message = MIMEMultipart('alternative')
                message['Subject'] = f'Notificación de {instance.receipt.name} {instance.voucher_number_full}'
                message['From'] = company.email_host_user
                message['To'] = client.user.email
                content = f'Estimado(a)\n\n{client.user.names.upper()}\n\n'
                content += f'{company.tradename} informa sobre documento electrónico emitido adjunto en formato XML Y PDF.\n\n'
                content += f'DOCUMENTO: {instance.receipt.name} {instance.voucher_number_full}\n'
                content += f"FECHA: {instance.date_joined.strftime('%Y-%m-%d')}\n"
                content += f'MONTO: {str(float(round(instance.total, 2)))}\n'
                content += f'CÓDIGO DE ACCESO: {instance.access_code}\n'
                content += f'AUTORIZACIÓN: {instance.access_code}'
                part = MIMEText(content)
                message.attach(part)
                with open(f'{settings.BASE_DIR}{instance.get_pdf_authorized()}', 'rb') as file:
                    part = MIMEApplication(file.read())
                    part.add_header('Content-Disposition', 'attachment', filename=f'{instance.access_code}.pdf')
                    message.attach(part)
                with open(f'{settings.BASE_DIR}{instance.get_xml_authorized()}', 'rb') as file:
                    part = MIMEApplication(file.read())
                    part.add_header('Content-Disposition', 'attachment', filename=f'{instance.access_code}.xml')
                    message.attach(part)
                if settings.DISABLE_REAL_EMAILS:
                    print(f'[DISABLE_REAL_EMAILS] Correo de {instance.receipt.name} {instance.voucher_number_full} no enviado (destinatario: {message["To"]})')
                else:
                    server = smtplib.SMTP(company.email_host, company.email_port)
                    server.starttls()
                    server.login(company.email_host_user, company.email_host_password)
                    server.sendmail(company.email_host_user, message['To'], message.as_string())
                    server.quit()
            instance.status = INVOICE_STATUS[2][0]
            instance.save()
            response['resp'] = True
        except Exception as e:
            response['error'] = str(e)
            self.create_voucher_errors(instance, response)
        return response

    def notify_retention_by_email(self, instance):
        """Envía al PROVEEDOR su comprobante de retención (XML y PDF
        autorizados). Si no tiene email, o el envío falla, la autorización ya
        obtenida no se pierde: el error queda registrado y se puede reenviar."""
        response = {'resp': False, 'stage': VOUCHER_STAGE[4][0]}
        try:
            company, provider = instance.company, instance.provider
            if provider.email:
                message = MIMEMultipart('alternative')
                message['Subject'] = f'Comprobante de retención {instance.voucher_number_full}'
                message['From'] = company.email_host_user
                message['To'] = provider.email
                content = f'Estimado(a)\n\n{provider.name.upper()}\n\n'
                content += f'{company.tradename} informa sobre el comprobante de retención electrónico emitido, adjunto en formato XML y PDF.\n\n'
                content += f'DOCUMENTO: {instance.receipt.name} {instance.voucher_number_full}\n'
                content += f"FECHA: {instance.date_joined.strftime('%Y-%m-%d')}\n"
                content += f'FACTURA SUSTENTO: {instance.purchase.number}\n'
                content += f'TOTAL RETENIDO: {float(round(instance.total, 2))}\n'
                content += f'CLAVE DE ACCESO: {instance.access_code}'
                message.attach(MIMEText(content))
                for path, extension in ((instance.get_pdf_authorized(), 'pdf'), (instance.get_xml_authorized(), 'xml')):
                    with open(f'{settings.BASE_DIR}{path}', 'rb') as file:
                        part = MIMEApplication(file.read())
                        part.add_header('Content-Disposition', 'attachment', filename=f'{instance.access_code}.{extension}')
                        message.attach(part)
                if settings.DISABLE_REAL_EMAILS:
                    print(f'[DISABLE_REAL_EMAILS] Retención {instance.voucher_number_full} no enviada (destinatario: {message["To"]})')
                else:
                    server = smtplib.SMTP(company.email_host, company.email_port)
                    server.starttls()
                    server.login(company.email_host_user, company.email_host_password)
                    server.sendmail(company.email_host_user, message['To'], message.as_string())
                    server.quit()
                instance.status = INVOICE_STATUS[2][0]
                instance.save()
            response['resp'] = True
        except Exception as e:
            response['error'] = str(e)
            self.create_voucher_errors(instance, response)
        return response

    def search_ruc_in_sri(self, ruc):
        response = {'error': 'El número de ruc es inválido'}
        url = f'https://srienlinea.sri.gob.ec/movil-servicios/api/v1.0/estadoTributario/{ruc}'
        try:
            r = requests.get(url, timeout=10, headers={'Accept': 'application/json'})
        except requests.exceptions.RequestException:
            response['error'] = 'No se pudo contactar el servicio del SRI. Verifica tu conexión a internet e intenta nuevamente.'
            return response
        try:
            data = r.json()
        except ValueError:
            response['error'] = 'El servicio del SRI no respondió con datos válidos. Puede estar temporalmente caído o bloqueando la consulta automática; intenta más tarde o ingresa los datos manualmente.'
            return response
        if r.status_code == requests.codes.ok:
            response = data
        else:
            response['error'] = data.get('mensaje', 'El SRI rechazó la consulta.')
        return response
