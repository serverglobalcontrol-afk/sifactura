"""Punto de entrada que usan las vistas del POS para contabilizar. Se importa
de forma perezosa (dentro de la función) desde `core.pos` para no acoplarlo
a la contabilidad ni crear imports circulares."""


def sync(kind, pk):
    """Contabiliza (o re-contabiliza, o anula) el origen `kind`:`pk`.

    NUNCA lanza una excepción: la contabilidad no debe tumbar una venta, una
    compra ni un cobro. Si algo falla se registra en el log y el asiento queda
    pendiente: "Contabilizar pendientes" lo recupera después."""
    try:
        from core.contabilidad.services.gate import company_keeps_accounting, is_enabled
        # Empresas que no llevan contabilidad: salida inmediata, sin tocar
        # ninguna tabla contable (que podría ni existir todavía).
        if not company_keeps_accounting():
            return None
        # Savepoint propio: si falla una consulta contable (p. ej. tablas aún
        # sin migrar), Postgres no deja abortada la transacción de la venta.
        from django.db import transaction
        with transaction.atomic():
            if not is_enabled():
                return None
            from core.contabilidad.services.posting import safe_sync
            return safe_sync(kind, pk)
    except Exception:
        import logging
        logging.getLogger('invoicepro').exception('Contabilidad: fallo al contabilizar %s:%s', kind, pk)
        return None
