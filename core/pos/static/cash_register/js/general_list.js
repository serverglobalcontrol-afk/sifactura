var input_date_range;
var cashRegister = {
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
        $('#data').DataTable({
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
            order: [[1, "desc"], [0, "asc"]],
            columns: [
                {data: "user.names"},
                {data: "date_joined"},
                {data: "opening_amount"},
                {data: "expected_cash_amount"},
                {data: "counted_amount"},
                {data: "difference"},
                {data: "closing_notes", defaultContent: '-'},
                {data: "id"},
            ],
            columnDefs: [
                {
                    targets: [2, 3, 4],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '$' + parseFloat(data).toFixed(2);
                    }
                },
                {
                    targets: [5],
                    class: 'text-center',
                    render: function (data, type, row) {
                        var cls = data == 0 ? 'text-success' : (data < 0 ? 'text-danger' : 'text-info');
                        return '<span class="' + cls + ' font-weight-bold">$' + parseFloat(data).toFixed(2) + '</span>';
                    }
                },
                {
                    targets: [7],
                    class: 'text-center',
                    render: function (data, type, row) {
                        var buttons = '<a href="/pos/caja/cierre/imprimir/' + row.id + '/" target="_blank" data-toggle="tooltip" title="Reimprimir" class="btn bg-blue btn-xs btn-flat"><i class="fas fa-print"></i></a> ';
                        buttons += '<a href="/pos/caja/cierres/general/consolidado/' + row.date_joined + '/" target="_blank" data-toggle="tooltip" title="Imprimir consolidado del día" class="btn bg-purple btn-xs btn-flat"><i class="fas fa-layer-group"></i></a>';
                        return buttons;
                    }
                },
            ],
            initComplete: function (settings, json) {
                $('[data-toggle="tooltip"]').tooltip();
                $(this).wrap('<div class="dataTables_scroll"><div/>');
            }
        });
    }
};

$(function () {

    input_date_range = $('input[name="date_range"]');

    input_date_range
        .daterangepicker({
                language: 'auto',
                startDate: moment().subtract(30, 'days'),
                endDate: new Date(),
                locale: {
                    format: 'YYYY-MM-DD',
                },
                autoApply: true,
            }
        )
        .on('change.daterangepicker apply.daterangepicker', function (ev, picker) {
            cashRegister.list(false);
        });

    $('.drp-buttons').hide();

    cashRegister.list(false);

    $('.btnSearchAll').on('click', function () {
        cashRegister.list(true);
    });
});
