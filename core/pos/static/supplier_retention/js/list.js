var tblRetention;
var input_date_range;

function ask(content, params, done) {
    submit_with_formdata({
        'params': params,
        'content': content,
        'success': function () {
            alert_sweetalert({
                'message': done,
                'timer': 2000,
                'callback': function () {
                    tblRetention.ajax.reload();
                }
            });
        }
    });
}

var retention = {
    list: function (all) {
        var parameters = {
            'action': 'search',
            'start_date': input_date_range.data('daterangepicker').startDate.format('YYYY-MM-DD'),
            'end_date': input_date_range.data('daterangepicker').endDate.format('YYYY-MM-DD'),
        };
        if (all) {
            parameters['start_date'] = '';
            parameters['end_date'] = '';
        }
        tblRetention = $('#data').DataTable({
            autoWidth: false,
            destroy: true,
            deferRender: true,
            ajax: {
                url: pathname,
                type: 'POST',
                headers: {'X-CSRFToken': csrftoken},
                data: parameters,
                dataSrc: ""
            },
            order: [[0, "desc"]],
            columns: [
                {data: "id"},
                {data: "voucher_number_full"},
                {data: "date_joined"},
                {data: "provider.name"},
                {data: "purchase.number"},
                {data: "status.name"},
                {data: "total_iva"},
                {data: "total_renta"},
                {data: "total"},
                {data: "id"},
            ],
            columnDefs: [
                {
                    targets: [-5],
                    class: 'text-center',
                    render: function (data, type, row) {
                        var name = row.status.name;
                        switch (row.status.id) {
                            case "without_authorizing":
                                return '<span class="badge badge-warning badge-pill">' + name + '</span>';
                            case "authorized":
                            case "authorized_and_sent_by_email":
                                return '<span class="badge badge-success badge-pill">' + name + '</span>';
                            default:
                                return '<span class="badge badge-danger badge-pill">' + name + '</span>';
                        }
                    }
                },
                {
                    targets: [-2, -3, -4],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '$' + data.toFixed(2);
                    }
                },
                {
                    targets: [-1],
                    class: 'text-center',
                    orderable: false,
                    render: function (data, type, row) {
                        var buttons = '<div class="btn-group" role="group">';
                        buttons += '<button type="button" class="btn btn-secondary btn-sm dropdown-toggle" data-toggle="dropdown" aria-expanded="false"><i class="fas fa-list"></i> Opciones</button>';
                        buttons += '<div class="dropdown-menu dropdown-menu-right">';
                        buttons += '<a class="dropdown-item" rel="detail"><i class="fas fa-folder-open"></i> Detalle</a>';
                        if (row.status.id === 'without_authorizing') {
                            buttons += '<a rel="generate_invoice" class="dropdown-item"><i class="fas fa-clipboard-check"></i> Generar retención electrónica</a>';
                            buttons += '<a href="' + pathname + 'delete/' + row.id + '/" class="dropdown-item text-danger"><i class="fas fa-trash"></i> Eliminar</a>';
                        } else if (['authorized', 'authorized_and_sent_by_email'].includes(row.status.id)) {
                            buttons += '<a rel="send_by_email" class="dropdown-item"><i class="fas fa-envelope"></i> Enviar al proveedor por email</a>';
                            buttons += '<a href="' + row.pdf_authorized + '" target="_blank" class="dropdown-item"><i class="fa-solid fa-file-pdf"></i> Imprimir pdf</a>';
                            buttons += '<a href="' + row.xml_authorized + '" target="_blank" class="dropdown-item"><i class="fas fa-file-code"></i> Descargar xml</a>';
                        }
                        buttons += '</div></div>';
                        return buttons;
                    }
                },
            ],
            initComplete: function (settings, json) {
                var total = json.reduce((a, b) => a + (b.total || 0), 0);
                $('.total').html('$' + total.toFixed(2));
            }
        });
    }
};

$(function () {
    input_date_range = $('input[name="date_range"]');

    $('#data tbody')
        .off()
        .on('click', 'a[rel="detail"]', function () {
            $('.tooltip').remove();
            var row = tblRetention.row(tblRetention.cell($(this).closest('td, li')).index().row).data();
            $('#tblDetails').DataTable({
                autoWidth: false,
                destroy: true,
                paging: false,
                searching: false,
                info: false,
                ajax: {
                    url: pathname,
                    type: 'POST',
                    headers: {'X-CSRFToken': csrftoken},
                    data: {'action': 'search_detail', 'id': row.id},
                    dataSrc: ""
                },
                columns: [
                    {data: "concept.kind.name"},
                    {data: "concept.code"},
                    {data: "concept.description"},
                    {data: "base"},
                    {data: "percentage"},
                    {data: "value"},
                ],
                columnDefs: [
                    {
                        targets: [-1, -3],
                        class: 'text-right',
                        render: function (data) {
                            return '$' + data.toFixed(2);
                        }
                    },
                    {targets: [-2], class: 'text-center'},
                ],
            });
            $('#myModalDetails').modal('show');
        })
        .on('click', 'a[rel="generate_invoice"]', function () {
            var row = tblRetention.row(tblRetention.cell($(this).closest('td, li')).index().row).data();
            var params = new FormData();
            params.append('action', 'generate_invoice');
            params.append('id', row.id);
            ask('¿Estás seguro de generar la retención electrónica?', params, 'Retención generada correctamente');
        })
        .on('click', 'a[rel="send_by_email"]', function () {
            var row = tblRetention.row(tblRetention.cell($(this).closest('td, li')).index().row).data();
            var params = new FormData();
            params.append('action', 'send_by_email');
            params.append('id', row.id);
            ask('¿Estás seguro de enviar el comprobante pdf/xml al proveedor por email?', params, 'Se ha enviado el comprobante por email');
        });

    $('#btnGeneratePending').on('click', function () {
        var params = new FormData();
        params.append('action', 'generate_pending');
        submit_with_formdata({
            'params': params,
            'content': '¿Está seguro de revisar y generar la autorización de todas las retenciones pendientes?',
            'success': function (request) {
                var message = request.authorized + ' retención(es) autorizada(s) correctamente.';
                if (request.failed) {
                    message += ' ' + request.failed + ' siguen pendientes o con error.';
                }
                if (request.stuck) {
                    message += ' ' + request.stuck + ' llevan más de 24h sin autorizar (revisa Errores de comprobantes).';
                }
                alert_sweetalert({
                    'title': 'Proceso finalizado',
                    'type': (request.failed || request.stuck) ? 'warning' : 'success',
                    'message': message,
                    'timer': null,
                    'callback': function () {
                        retention.list(true);
                    }
                });
            }
        });
    });

    input_date_range
        .daterangepicker({
            language: 'auto',
            startDate: new Date(),
            locale: {format: 'YYYY-MM-DD'},
            autoApply: true,
        })
        .on('apply.daterangepicker', function () {
            retention.list(false);
        });
    $('.drp-buttons').hide();

    retention.list(true);

    $('.btnSearchAll').on('click', function () {
        retention.list(true);
    });
});
