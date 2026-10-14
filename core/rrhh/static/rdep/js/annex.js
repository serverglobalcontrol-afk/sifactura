function esc(value) {
    return $('<div>').text(value == null ? '' : value).html();
}

function money(value) {
    return '$' + (parseFloat(value) || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function call(params, done) {
    $.ajax({
        url: pathname,
        type: 'POST',
        data: params,
        headers: {'X-CSRFToken': csrftoken},
        dataType: 'json',
        beforeSend: function () {
            loading({'text': '...'});
        },
        success: function (request) {
            if (request.hasOwnProperty('error')) {
                message_error(request.error);
                return false;
            }
            done(request);
        },
        error: function (jqXHR, textStatus, errorThrown) {
            message_error(errorThrown + ' ' + textStatus);
        },
        complete: function () {
            $.LoadingOverlay('hide');
        }
    });
}

function issuesHtml(item) {
    var icons = {error: 'fa-times-circle text-danger', warning: 'fa-exclamation-triangle text-warning', info: 'fa-info-circle text-info'};
    var html = '';
    $.each(item.issues, function (index, issue) {
        html += '<li><i class="fas ' + icons[issue.level] + '"></i> <b>' + esc(issue.document) + ':</b> ' + esc(issue.message) + '</li>';
    });
    if (item.xsd_errors.length) {
        html += '<li><i class="fas fa-times-circle text-danger"></i> <b>Esquema del SRI:</b> el XML todavía no lo cumple (' + esc(item.xsd_errors.join(' | ')) + ').</li>';
    }
    return html ? '<ul class="list-unstyled mb-0">' + html + '</ul>' : '<span class="text-muted">Sin observaciones.</span>';
}

function render(item) {
    var badge = (item.xsd_errors.length || item.errors) ? '<span class="badge badge-danger">Con errores</span>'
        : (item.warnings ? '<span class="badge badge-warning">Listo, con avisos</span>' : '<span class="badge badge-success">Listo</span>');
    var html = '<h6 class="font-weight-bold">RDEP ' + item.year + ' ' + badge + ' <small class="text-muted">' + item.count + ' empleado(s)</small></h6>';
    html += '<div class="table-responsive"><table class="table table-bordered table-sm" style="width:100%;"><thead><tr>' +
        '<th>Empleado</th><th class="text-right">Ingresos gravados</th><th class="text-right">Aporte IESS</th><th class="text-right">Base imponible</th>' +
        '<th class="text-right">Impuesto causado</th><th class="text-right">Rebaja gastos</th><th class="text-right">Impuesto a pagar</th>' +
        '<th class="text-right">Retenido</th><th class="text-center">Datos anuales</th></tr></thead><tbody>';
    if (!item.employees.length) {
        html += '<tr><td colspan="9" class="text-center text-muted">No hay empleados con nómina en ' + item.year + ': el anexo se presenta en cero.</td></tr>';
    }
    $.each(item.employees, function (index, e) {
        html += '<tr><td>' + esc(e.name) + '</td><td class="text-right">' + money(e.income) + '</td><td class="text-right">' + money(e.iess) + '</td>' +
            '<td class="text-right">' + money(e.base) + '</td><td class="text-right">' + money(e.caused) + '</td><td class="text-right">' + money(e.rebate) + '</td>' +
            '<td class="text-right">' + money(e.after) + '</td><td class="text-right">' + money(e.withheld) + '</td>' +
            '<td class="text-center"><a class="btn btn-' + (e.manual ? 'success' : 'warning') + ' btn-xs btn-flat btn-manual" data-employee="' + e.id + '">' +
            '<i class="fas fa-edit"></i> ' + (e.manual ? 'Editar' : 'Registrar') + '</a></td></tr>';
    });
    html += '</tbody></table></div>';
    html += '<div class="bg-light p-2">' + issuesHtml(item) + '</div>';
    $('#annexResult').html(html);
    var download = $('#btnDownload');
    if (item.valid) {
        download.removeClass('disabled').attr('href', pathname + '?action=download&year=' + item.year);
    } else {
        download.addClass('disabled').attr('href', '#');
    }
}

function preview() {
    call({action: 'preview', year: $('#annexYear').val()}, render);
}

$(function () {
    $('#btnPreview').on('click', preview);

    $('#annexResult').on('click', '.btn-manual', function () {
        var id = $(this).data('employee');
        call({action: 'get_manual', year: $('#annexYear').val(), employee: id}, function (request) {
            $('#manualEmployee').text(request.employee + ' (' + $('#annexYear').val() + ')');
            $('#manualEmployeeId').val(id);
            $('.manual-field').each(function () {
                $(this).val((request.values[$(this).data('key')] || 0).toFixed(2));
            });
            $('#myModalManual').modal('show');
        });
    });

    $('#btnSaveManual').on('click', function () {
        var params = {action: 'save_manual', year: $('#annexYear').val(), employee: $('#manualEmployeeId').val()};
        $('.manual-field').each(function () {
            params[$(this).data('key')] = $(this).val();
        });
        call(params, function () {
            $('#myModalManual').modal('hide');
            preview();
        });
    });
});
