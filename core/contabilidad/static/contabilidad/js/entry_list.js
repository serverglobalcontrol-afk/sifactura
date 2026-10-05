var tblEntry;

function money(value) {
    return '$' + parseFloat(value || 0).toFixed(2);
}

function search_entries() {
    tblEntry = $('#data').DataTable({
        autoWidth: false,
        destroy: true,
        deferRender: true,
        order: [[1, 'desc'], [0, 'desc']],
        ajax: {
            url: pathname,
            type: 'POST',
            headers: {'X-CSRFToken': csrftoken},
            data: {
                'action': 'search',
                'start_date': $('#filterStart').val(),
                'end_date': $('#filterEnd').val(),
                'source_type': $('#filterSource').val(),
                'status': $('#filterStatus').val(),
            },
            dataSrc: ''
        },
        columns: [
            {data: 'number'},
            {data: 'date'},
            {data: 'created_at'},
            {data: 'source_type.name'},
            {data: 'description'},
            {data: 'total_debit'},
            {data: 'total_credit'},
            {data: 'status.name'},
            {data: 'id'},
        ],
        columnDefs: [
            {
                targets: [5, 6],
                class: 'text-right',
                render: function (data) {
                    return money(data);
                }
            },
            {
                targets: [7],
                class: 'text-center',
                render: function (data, type, row) {
                    return row.status.id === 'voided' ? '<span class="badge badge-danger">Anulado</span>' : '<span class="badge badge-success">Registrado</span>';
                }
            },
            {
                targets: [-1],
                class: 'text-center',
                orderable: false,
                render: function (data, type, row) {
                    var buttons = '<a rel="detail" data-toggle="tooltip" title="Ver asiento" class="btn btn-info btn-xs btn-flat"><i class="fas fa-search"></i></a> ';
                    var manual = row.source_type.id === 'manual' || row.source_type.id === 'bank_move';
                    if (manual && row.status.id === 'posted') {
                        buttons += '<a rel="void" data-toggle="tooltip" title="Anular" class="btn btn-danger btn-xs btn-flat"><i class="fas fa-ban"></i></a>';
                    }
                    return buttons;
                }
            },
        ],
        initComplete: function () {
            $('[data-toggle="tooltip"]').tooltip();
            $(this).wrap('<div class="dataTables_scroll"><div/>');
        }
    });
}

$(function () {
    search_entries();

    $('#btnSearch').on('click', search_entries);

    $('#data tbody')
        .on('click', 'a[rel="detail"]', function () {
            $('.tooltip').remove();
            var row = tblEntry.row($(this).closest('tr')).data();
            execute_ajax_request({
                'params': {'action': 'detail', 'id': row.id},
                'success': function (data) {
                    $('#detailTitle').text(data.number + ' - ' + data.date);
                    $('#detailDescription').text(data.description);
                    $('#detailMeta').text('Origen: ' + data.source_type.name + (data.reference ? ' | Comprobante N° ' + data.reference : '') + ' | Registrado: ' + data.created_at + ' | Estado: ' + data.status.name + (data.void_reason ? ' (' + data.void_reason + ')' : ''));
                    var body = '';
                    data.lines.forEach(function (line) {
                        body += '<tr><td>' + line.account + '</td><td>' + (line.description || line.third_party || '') + '</td>' +
                            '<td class="text-right">' + (line.debit ? money(line.debit) : '') + '</td>' +
                            '<td class="text-right">' + (line.credit ? money(line.credit) : '') + '</td></tr>';
                    });
                    $('#tblDetail tbody').html(body);
                    $('#detailDebit').text(money(data.total_debit));
                    $('#detailCredit').text(money(data.total_credit));
                    $('#modalDetail').modal('show');
                }
            });
        })
        .on('click', 'a[rel="void"]', function () {
            $('.tooltip').remove();
            var row = tblEntry.row($(this).closest('tr')).data();
            $.confirm({
                title: 'Anular ' + row.number,
                icon: 'fas fa-ban',
                theme: 'material',
                type: 'red',
                columnClass: 'small',
                content: '<input type="text" class="form-control" id="voidReason" placeholder="Motivo de la anulación" autocomplete="off">',
                buttons: {
                    ok: {
                        text: 'Anular',
                        btnClass: 'btn-red',
                        action: function () {
                            var reason = this.$content.find('#voidReason').val();
                            execute_ajax_request({
                                'params': {'action': 'void', 'id': row.id, 'reason': reason},
                                'success': function () {
                                    tblEntry.ajax.reload();
                                }
                            });
                        }
                    },
                    cancel: {text: 'Cancelar'}
                }
            });
        });

    $('#btnPostPending').on('click', function () {
        $('#pendingResult').empty();
        $('#modalPending').modal('show');
    });

    $('#btnRunPending').on('click', function () {
        var start = $('#pendingStart').val();
        var end = $('#pendingEnd').val();
        if (!start || !end) {
            message_error('Elige la fecha inicial y la final.');
            return false;
        }
        execute_ajax_request({
            'params': {'action': 'post_pending', 'start_date': start, 'end_date': end},
            'success': function (data) {
                var s = data.summary;
                var html = '<div class="alert alert-success mb-2">Creados: <b>' + s.created + '</b> | Actualizados: <b>' + s.updated +
                    '</b> | Anulados: <b>' + s.voided + '</b> | Sin cambios: <b>' + s.unchanged + '</b> | Omitidos (fuera de rango o antes del inicio): <b>' + s.skipped +
                    '</b> | Bloqueados (período cerrado): <b>' + s.blocked + '</b></div>';
                if (data.errors_total > 0) {
                    html += '<div class="alert alert-danger"><b>' + data.errors_total + ' documento(s) con error</b> (revisa la configuración de cuentas):<ul class="mb-0">';
                    data.errors.forEach(function (e) {
                        html += '<li>' + e + '</li>';
                    });
                    html += '</ul></div>';
                }
                $('#pendingResult').html(html);
                tblEntry.ajax.reload();
            }
        });
    });
});
