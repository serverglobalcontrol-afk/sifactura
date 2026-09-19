var tblRetentionList;
var input_date_range;
var retention_list = {
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
        tblRetentionList = $('#data').DataTable({
            autoWidth: false,
            destroy: true,
            deferRender: true,
            ajax: {
                url: pathname,
                type: 'POST',
                headers: {
                    'X-CSRFToken': csrftoken
                },
                data: parameters,
                dataSrc: ""
            },
            order: [[0, "desc"]],
            columns: [
                {data: "id"},
                {data: "date_joined"},
                {data: "sale.voucher_number_full"},
                {data: "sale.client.user.names"},
                {data: "sale.total"},
                {data: "iva_retained"},
                {data: "income_tax_retained"},
                {data: "total_retained"},
                {data: "agent_name", defaultContent: '-'},
                {data: "created_by.names", defaultContent: '-'},
                {data: "id"},
            ],
            columnDefs: [
                {
                    targets: [-2, -3, -4, -5, -6],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '$' + parseFloat(data).toFixed(2);
                    }
                },
                {
                    targets: [-1],
                    class: 'text-center',
                    render: function (data, type, row) {
                        var buttons = '<div class="btn-group" role="group">';
                        buttons += '<div class="btn-group" role="group">';
                        buttons += '<button type="button" class="btn btn-secondary btn-sm dropdown-toggle" data-toggle="dropdown" aria-expanded="false"><i class="fas fa-list"></i> Opciones</button>';
                        buttons += '<div class="dropdown-menu dropdown-menu-right">';
                        if (row.xml_file) {
                            buttons += '<a href="' + row.xml_file + '" target="_blank" class="dropdown-item"><i class="fas fa-file-code"></i> Descargar xml</a>';
                        }
                        buttons += '<a rel="delete" class="dropdown-item"><i class="fas fa-trash-alt"></i> Eliminar</a>';
                        buttons += '</div></div></div>';
                        return buttons;
                    }
                },
            ],
            initComplete: function (settings, json) {
                var total = json.reduce((a, b) => a + (b.total_retained || 0), 0);
                $('.total').html('$' + total.toFixed(2));
            }
        });
    }
}

$(function () {
    input_date_range = $('input[name="date_range"]');

    $('#data tbody')
        .on('click', 'a[rel="delete"]', function () {
            $('.tooltip').remove();
            var tr = tblRetentionList.cell($(this).closest('td, li')).index();
            var row = tblRetentionList.row(tr.row).data();
            dialog_action({
                content: '¿Esta seguro de eliminar esta retención? El saldo pendiente de la factura volverá a aumentar por ese valor.',
                success: function () {
                    loading({'text': '...'});
                    $.ajax({
                        url: '/pos/sale/admin/retention/delete/' + row.id + '/',
                        type: 'POST',
                        dataType: 'json',
                        headers: {'X-CSRFToken': csrftoken},
                        success: function (response) {
                            if (response && response.error) {
                                message_error(response.error);
                                return;
                            }
                            retention_list.list(true);
                        },
                        complete: function () {
                            $.LoadingOverlay('hide');
                        }
                    });
                },
                cancel: function () {
                }
            });
        });

    input_date_range
        .daterangepicker({
                language: 'auto',
                startDate: new Date(),
                locale: {
                    format: 'YYYY-MM-DD',
                },
                autoApply: true,
            }
        )
        .on('apply.daterangepicker', function (ev, picker) {
            retention_list.list(false);
        });

    $('.drp-buttons').hide();

    // Igual que en Notas de Crédito: se muestran las últimas retenciones
    // registradas (sin filtrar por el rango de fechas de hoy), ya ordenadas
    // por id descendente y paginadas de 10 en 10.
    retention_list.list(true);

    $('.btnSearchAll').on('click', function () {
        retention_list.list(true);
    });
});
