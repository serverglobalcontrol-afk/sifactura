// Se genera una sola vez al cargar el formulario: si el mismo envío llega dos
// veces (doble clic, reintento de red) el servidor no emite dos retenciones.
var retention_idempotency_key = (window.crypto && window.crypto.randomUUID) ? window.crypto.randomUUID() : (Date.now().toString(36) + Math.random().toString(36).slice(2));

function conceptsOf(kind) {
    return CONCEPTS.filter(function (c) {
        return c.kind.id === kind;
    });
}

function addRow(kind) {
    var options = '<option value="">--- Seleccione un concepto ---</option>';
    conceptsOf(kind).forEach(function (c) {
        options += '<option value="' + c.id + '">' + c.code + ' - ' + $('<span>').text(c.description).html() + (c.percentage === null ? ' (% variable)' : ' (' + c.percentage + '%)') + '</option>';
    });
    // Base por defecto: el subtotal para renta y el IVA de la compra para IVA.
    var base = kind === 'renta' ? PURCHASE.subtotal : PURCHASE.total_iva;
    var row = '<tr data-kind="' + kind + '">' +
        '<td class="text-center"><a rel="remove" class="btn btn-danger btn-xs btn-flat"><i class="fas fa-times"></i></a></td>' +
        '<td>' + (kind === 'renta' ? 'Renta' : 'IVA') + '</td>' +
        '<td><select class="form-control form-control-sm concept">' + options + '</select></td>' +
        '<td><input type="number" min="0" step="0.01" class="form-control form-control-sm text-right base" value="' + base.toFixed(2) + '"></td>' +
        '<td><input type="number" min="0" max="100" step="0.01" class="form-control form-control-sm text-right percentage" readonly></td>' +
        '<td class="text-right value font-weight-bold">$0.00</td>' +
        '</tr>';
    $('#tblItems tbody').append(row);
}

function recalculate() {
    var renta = 0;
    var iva = 0;
    $('#tblItems tbody tr').each(function () {
        var base = parseFloat($(this).find('.base').val()) || 0;
        var pct = parseFloat($(this).find('.percentage').val()) || 0;
        var value = Math.round(base * pct) / 100;
        $(this).find('.value').text('$' + value.toFixed(2));
        if ($(this).data('kind') === 'renta') {
            renta += value;
        } else {
            iva += value;
        }
    });
    $('.renta').text('$' + renta.toFixed(2));
    $('.iva').text('$' + iva.toFixed(2));
    $('.total').text('$' + (renta + iva).toFixed(2));
}

$(function () {
    $('#btnAddRenta').on('click', function () {
        addRow('renta');
    });
    $('#btnAddIva').on('click', function () {
        addRow('iva');
    });

    $('#tblItems tbody')
        .on('click', 'a[rel="remove"]', function () {
            $(this).closest('tr').remove();
            recalculate();
        })
        .on('change', '.concept', function () {
            var tr = $(this).closest('tr');
            var concept = CONCEPTS.find(function (c) {
                return String(c.id) === $(this).val();
            }.bind(this));
            var pct = tr.find('.percentage');
            if (!concept) {
                pct.val('').prop('readonly', true);
            } else if (concept.percentage === null) {
                // El catálogo del SRI no fija un porcentaje (varía según el caso): se ingresa a mano.
                pct.val('').prop('readonly', false).attr('placeholder', concept.note || 'varía');
            } else {
                pct.val(parseFloat(concept.percentage).toFixed(2)).prop('readonly', true);
            }
            recalculate();
        })
        .on('input', '.base, .percentage', recalculate);

    $('#frmForm').on('submit', function (e) {
        e.preventDefault();
        var items = [];
        var invalid = false;
        $('#tblItems tbody tr').each(function () {
            var concept = $(this).find('.concept').val();
            var base = $(this).find('.base').val();
            var pct = $(this).find('.percentage').val();
            if (!concept || !(parseFloat(base) > 0) || pct === '' || isNaN(parseFloat(pct))) {
                invalid = true;
                return;
            }
            items.push({'concept': concept, 'base': base, 'percentage': pct});
        });
        if (!items.length || invalid) {
            message_error('Completa todos los conceptos: concepto, base mayor a cero y porcentaje.');
            return false;
        }
        var params = new FormData();
        params.append('action', 'add');
        params.append('purchase', $('input[name="purchase"]').val());
        params.append('observations', $('input[name="observations"]').val());
        params.append('items', JSON.stringify(items));
        params.append('idempotency_key', retention_idempotency_key);
        params.append('csrfmiddlewaretoken', $('input[name="csrfmiddlewaretoken"]').val());
        submit_with_formdata({
            'params': params,
            'form': this,
            'content': '¿Emitir la retención? Se firmará y enviará al SRI, y el número quedará consumido.',
        });
    });
});
