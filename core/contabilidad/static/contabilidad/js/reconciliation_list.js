var tblStatements;

function statementMoney(value) {
    return '$' + (parseFloat(value) || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

$(function () {
    tblStatements = $('#data').DataTable({
        autoWidth: false,
        destroy: true,
        deferRender: true,
        order: [[1, 'desc']],
        ajax: {
            url: pathname,
            type: 'POST',
            headers: {'X-CSRFToken': csrftoken},
            data: {'action': 'search'},
            dataSrc: ''
        },
        columns: [
            {data: 'bank_account'},
            {data: 'date_to'},
            {data: 'file_name'},
            {data: 'closing_balance'},
            {data: 'matched'},
            {data: 'status.name'},
            {data: 'id'},
        ],
        columnDefs: [
            {
                targets: [1],
                render: function (data, type, row) {
                    return row.date_from + ' a ' + row.date_to;
                }
            },
            {
                targets: [2],
                render: function (data, type, row) {
                    return $('<div>').text(data).html() + ' <span class="badge badge-secondary">' + row.source.name + '</span>';
                }
            },
            {targets: [3], class: 'text-right', render: statementMoney},
            {
                targets: [4],
                class: 'text-center',
                render: function (data, type, row) {
                    return row.matched + ' de ' + row.lines;
                }
            },
            {
                targets: [5],
                class: 'text-center',
                render: function (data, type, row) {
                    return row.status.id === 'reconciled'
                        ? '<span class="badge badge-success">Conciliado</span>'
                        : '<span class="badge badge-warning">En proceso</span>';
                }
            },
            {
                targets: [-1],
                class: 'text-center',
                orderable: false,
                render: function (data, type, row) {
                    return '<a href="' + pathname + row.id + '/" class="btn btn-primary btn-xs btn-flat"><i class="fas fa-balance-scale"></i> Abrir</a> ' +
                        '<a rel="delete" class="btn btn-danger btn-xs btn-flat"><i class="fas fa-trash"></i></a>';
                }
            },
        ],
        initComplete: function () {
            $(this).wrap('<div class="dataTables_scroll"><div/>');
        }
    });

    $('#btnNewStatement').on('click', function () {
        $('#myModalImport').modal('show');
    });

    $('#btnImport').on('click', function () {
        var form = document.getElementById('frmImport');
        if (!form.reportValidity()) {
            return false;
        }
        var params = new FormData(form);
        params.append('action', 'import');
        $.ajax({
            url: pathname,
            type: 'POST',
            data: params,
            headers: {'X-CSRFToken': csrftoken},
            dataType: 'json',
            processData: false,
            contentType: false,
            beforeSend: function () {
                loading({'text': 'Leyendo el estado de cuenta...'});
            },
            success: function (request) {
                if (request.hasOwnProperty('error')) {
                    message_error(request.error);
                    return false;
                }
                $('#myModalImport').modal('hide');
                var message = request.lines + ' movimiento(s) cargados; ' + request.matched + ' conciliados automáticamente.';
                if (request.warnings && request.warnings.length) {
                    message += '\n\n' + request.warnings.join('\n');
                }
                alert_sweetalert({
                    'title': 'Estado de cuenta cargado',
                    'type': request.warnings && request.warnings.length ? 'warning' : 'success',
                    'message': message,
                    'timer': null,
                    'callback': function () {
                        location.href = pathname + request.id + '/';
                    }
                });
            },
            error: function (jqXHR, textStatus, errorThrown) {
                message_error(errorThrown + ' ' + textStatus);
            },
            complete: function () {
                $.LoadingOverlay('hide');
            }
        });
    });

    $('#data tbody').on('click', 'a[rel="delete"]', function () {
        var row = tblStatements.row($(this).closest('tr')).data();
        dialog_action({
            'title': 'Eliminar conciliación',
            'content': 'Se elimina el estado de cuenta cargado (no los asientos). ¿Desea continuar?',
            'success': function () {
                execute_ajax_request({
                    'params': {'action': 'delete', 'id': row.id},
                    'success': function () {
                        tblStatements.ajax.reload();
                    }
                });
            },
            'cancel': function () {
            }
        });
    });
});
