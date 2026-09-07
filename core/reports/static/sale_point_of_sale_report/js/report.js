var input_date_range;
var select_employee;
var current_date;
var tblReport;
var columns = [];
var report = {
    initTable: function () {
        tblReport = $('#tblReport').DataTable({
            autoWidth: false,
            destroy: true,
        });
        tblReport.settings()[0].aoColumns.forEach(function (value, index, array) {
            columns.push(value.sWidthOrig);
        });
    },
    list: function (all) {
        var parameters = {
            'action': 'search_report',
            'start_date': input_date_range.data('daterangepicker').startDate.format('YYYY-MM-DD'),
            'end_date': input_date_range.data('daterangepicker').endDate.format('YYYY-MM-DD'),
            'employee': select_employee.val() || '',
        };
        if (all) {
            parameters['start_date'] = '';
            parameters['end_date'] = '';
        }
        tblReport = $('#tblReport').DataTable({
            destroy: true,
            autoWidth: false,
            ajax: {
                url: pathname,
                type: 'POST',
                headers: {
                    'X-CSRFToken': csrftoken
                },
                data: parameters,
                dataSrc: ''
            },
            order: [[0, 'desc']],
            paging: false,
            ordering: true,
            searching: false,
            dom: 'Bfrtip',
            buttons: [
                {
                    extend: 'excelHtml5',
                    text: ' <i class="fas fa-file-excel"></i> Descargar Excel',
                    titleAttr: 'Excel',
                    className: 'btn btn-success btn-flat btn-sm'
                },
                {
                    extend: 'pdfHtml5',
                    text: '<i class="fas fa-file-pdf"></i> Descargar Pdf',
                    titleAttr: 'PDF',
                    className: 'btn btn-danger btn-flat btn-sm',
                    download: 'open',
                    orientation: 'landscape',
                    pageSize: 'LEGAL',
                    customize: function (doc) {
                        apply_report_pdf_layout(doc, columns);
                    }
                }
            ],
            columns: [
                {data: "date_joined"},
                {data: "employee.names"},
                {data: "ventas_efectivo"},
                {data: "ventas_transferencia"},
                {data: "ventas_tarjeta"},
                {data: "ventas_credito"},
                {data: "total"},
            ],
            columnDefs: [
                {
                    targets: [-1, -2, -3, -4, -5],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '$' + data.toFixed(2);
                    }
                }
            ],
            rowCallback: function (row, data, index) {

            },
            footerCallback: function (row, data, start, end, display) {
                var sumColumn = function (field) {
                    return data.reduce(function (a, b) {
                        return a + (parseFloat(b[field]) || 0);
                    }, 0);
                };
                $('#footerVentasEfectivo').html('$' + sumColumn('ventas_efectivo').toFixed(2));
                $('#footerVentasTransferencia').html('$' + sumColumn('ventas_transferencia').toFixed(2));
                $('#footerVentasTarjeta').html('$' + sumColumn('ventas_tarjeta').toFixed(2));
                $('#footerVentasCredito').html('$' + sumColumn('ventas_credito').toFixed(2));
                $('#footerTotal').html('$' + sumColumn('total').toFixed(2));
            },
            initComplete: function (settings, json) {
                $(this).wrap('<div class="dataTables_scroll"><div/>');
            }
        });
    }
};

$(function () {

    current_date = new moment().format('YYYY-MM-DD');
    input_date_range = $('input[name="date_range"]');
    select_employee = $('select[name="employee"]');

    $('.select2').select2({
        placeholder: 'Todos los Puntos de Venta',
        allowClear: true,
        language: 'es',
        theme: 'bootstrap4'
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
        .on('change.daterangepicker apply.daterangepicker', function (ev, picker) {
            report.list(false);
        });

    select_employee.on('change', function () {
        report.list(false);
    });

    $('.drp-buttons').hide();

    report.initTable();

    report.list(false);

    $('.btnSearchAll').on('click', function () {
        report.list(true);
    });
});
