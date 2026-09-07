var input_date_range;
var select_product;
var input_voucher_number;
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
    list: function () {
        var parameters = {
            'action': 'search_report',
            'start_date': input_date_range.data('daterangepicker') ? input_date_range.data('daterangepicker').startDate.format('YYYY-MM-DD') : '',
            'end_date': input_date_range.data('daterangepicker') ? input_date_range.data('daterangepicker').endDate.format('YYYY-MM-DD') : '',
            'product_id': JSON.stringify(select_product.select2('data').map(value => value.id)),
            'voucher_number': input_voucher_number.val().trim(),
        };
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
            paging: true,
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
                {data: "voucher_number_full"},
                {data: "receipt"},
                {data: "client"},
                {data: "client_dni"},
                {data: "product.name"},
                {data: "cant"},
                {data: "price"},
                {data: "total"},
            ],
            columnDefs: [
                {
                    targets: [1, 2, 4, 6],
                    class: 'text-center',
                },
                {
                    targets: [7, 8],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '$' + data.toFixed(2);
                    }
                }
            ],
            rowCallback: function (row, data, index) {

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
    select_product = $('select[name="product"]');
    input_voucher_number = $('input[name="voucher_number"]');

    $('.select2').select2({
        placeholder: 'Todos los productos',
        language: 'es',
        theme: 'bootstrap4'
    });

    input_date_range
        .daterangepicker({
                language: 'auto',
                startDate: moment().startOf('month'),
                endDate: moment(),
                locale: {
                    format: 'YYYY-MM-DD',
                },
                autoApply: true,
            }
        );

    $('.drp-buttons').hide();

    report.initTable();

    $('.btnSearch').on('click', function () {
        report.list();
    });

    input_voucher_number.on('keypress', function (e) {
        if (e.which === 13) {
            e.preventDefault();
            report.list();
        }
    });
});
