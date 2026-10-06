// Anexo Transaccional Simplificado: revisión por meses y descarga de los ATmmaaaa.zip.
function esc(value) {
    return $('<div>').text(value == null ? '' : value).html();
}

function money(value) {
    return '$' + (parseFloat(value) || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function downloadUrl(start, end) {
    return pathname + '?action=download&start=' + encodeURIComponent(start) + '&end=' + encodeURIComponent(end);
}

function monthKey(item) {
    return item.year + '-' + ('0' + item.month).slice(-2);
}

function statusBadge(item) {
    if (item.xsd_errors.length || item.errors) {
        return '<span class="badge badge-danger">Con errores</span>';
    }
    if (item.warnings) {
        return '<span class="badge badge-warning">Listo, con avisos</span>';
    }
    return '<span class="badge badge-success">Listo</span>';
}

function issuesHtml(item) {
    var html = '';
    var icons = {error: 'fa-times-circle text-danger', warning: 'fa-exclamation-triangle text-warning', info: 'fa-info-circle text-info'};
    $.each(item.issues, function (index, issue) {
        html += '<li><i class="fas ' + icons[issue.level] + '"></i> <b>' + esc(issue.document) + ':</b> ' + esc(issue.message) + '</li>';
    });
    if (item.xsd_errors.length) {
        html += '<li><i class="fas fa-times-circle text-danger"></i> <b>Esquema del SRI:</b> el XML todavía no lo cumple (' + esc(item.xsd_errors.join(' | ')) + '). Suele resolverse al corregir los errores de arriba.</li>';
    }
    return html ? '<ul class="list-unstyled mb-0">' + html + '</ul>' : '<span class="text-muted">Sin observaciones.</span>';
}

function renderResult(months) {
    var html = '<div class="table-responsive"><table class="table table-bordered table-sm" style="width:100%;"><thead><tr>' +
        '<th>Mes</th><th class="text-right">Compras</th><th class="text-right">Base compras</th><th class="text-right">Facturas</th>' +
        '<th class="text-right">Notas de crédito</th><th class="text-right">Anuladas</th><th class="text-right">Ventas netas</th>' +
        '<th class="text-center">Estado</th><th class="text-center">Archivo</th></tr></thead><tbody>';
    var allValid = months.length > 0;
    $.each(months, function (index, item) {
        var key = monthKey(item);
        var button = item.valid
            ? '<a class="btn btn-success btn-xs" href="' + downloadUrl(key, key) + '"><i class="fas fa-download"></i> ' + esc(item.file) + '</a>'
            : '<button class="btn btn-secondary btn-xs" disabled><i class="fas fa-lock"></i> ' + esc(item.file) + '</button>';
        allValid = allValid && item.valid;
        html += '<tr><td><b>' + esc(item.label) + '</b></td>' +
            '<td class="text-right">' + item.purchases + '</td><td class="text-right">' + money(item.purchases_base) + '</td>' +
            '<td class="text-right">' + item.invoices + '</td><td class="text-right">' + item.credit_notes + '</td>' +
            '<td class="text-right">' + item.canceled + '</td><td class="text-right">' + money(item.total_sales) + '</td>' +
            '<td class="text-center">' + statusBadge(item) + '</td><td class="text-center">' + button + '</td></tr>' +
            '<tr><td colspan="9" class="bg-light">' + issuesHtml(item) + '</td></tr>';
    });
    html += '</tbody></table></div>';
    $('#atsResult').html(html);
    $('#btnDownloadAll').prop('disabled', !allValid || months.length < 2);
}

$(function () {
    $('#btnPreview').on('click', function () {
        var start = $('#startMonth').val();
        var end = $('#endMonth').val();
        if (!start || !end) {
            message_error('Elige el mes inicial y el mes final.');
            return false;
        }
        $.ajax({
            url: pathname,
            type: 'POST',
            data: {action: 'preview', start: start, end: end},
            headers: {'X-CSRFToken': csrftoken},
            dataType: 'json',
            beforeSend: function () {
                loading({'text': 'Revisando el ATS...'});
            },
            success: function (request) {
                if (request.hasOwnProperty('error')) {
                    message_error(request.error);
                    return false;
                }
                renderResult(request.months);
            },
            error: function (jqXHR, textStatus, errorThrown) {
                message_error(errorThrown + ' ' + textStatus);
            },
            complete: function () {
                $.LoadingOverlay('hide');
            }
        });
    });

    $('#btnDownloadAll').on('click', function () {
        window.location.href = downloadUrl($('#startMonth').val(), $('#endMonth').val());
    });
});
