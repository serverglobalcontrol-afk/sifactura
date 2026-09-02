# El sistema factura en USD y todos los documentos (RIDE, tickets, roles de
# pago) usan punto decimal, no coma. El locale 'es' de Django trae coma por
# defecto, lo que hacia que CUALQUIER numero renderizado con {{ valor }} o
# |floatformat en una plantilla (no via JS/JSON) saliera como "28,43" en vez
# de "28.43". Este modulo (activado via FORMAT_MODULE_PATH) sobreescribe solo
# el separador de miles/decimales para el locale 'es-ec' -> 'es'.
DECIMAL_SEPARATOR = '.'
THOUSAND_SEPARATOR = ','
NUMBER_GROUPING = 3
