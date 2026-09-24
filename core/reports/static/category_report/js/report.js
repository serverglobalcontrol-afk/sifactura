var input_date_range;
var current_date;
var current_start_date = '';
var current_end_date = '';
var tblReport;
var tblDetail;
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
        };
        if (all) {
            parameters['start_date'] = '';
            parameters['end_date'] = '';
        }
        current_start_date = parameters['start_date'];
        current_end_date = parameters['end_date'];
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
            order: [[2, 'desc']],
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
                {data: "category"},
                {data: "cantidad"},
                {data: "total"},
            ],
            columnDefs: [
                {
                    targets: [0],
                    render: function (data, type, row) {
                        return '<a rel="detail" data-category-id="' + row.category_id + '" style="cursor: pointer; text-decoration: underline;">' + data + '</a>';
                    }
                },
                {
                    targets: [1],
                    class: 'text-center',
                },
                {
                    targets: [2],
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
                var total = json.reduce(function (a, b) {
                    return a + (parseFloat(b.total) || 0);
                }, 0);
                $('.total').html('$' + total.toFixed(2));
            }
        });
    },
    listDetail: function (category_id) {
        tblDetail = $('#tblDetail').DataTable({
            autoWidth: false,
            destroy: true,
            searching: false,
            paging: false,
            ajax: {
                url: pathname,
                type: 'POST',
                headers: {
                    'X-CSRFToken': csrftoken
                },
                data: {
                    'action': 'search_detail',
                    'category_id': category_id,
                    'start_date': current_start_date,
                    'end_date': current_end_date,
                },
                dataSrc: ''
            },
            columns: [
                {data: 'date_joined'},
                {data: 'voucher_number_full'},
                {data: 'product'},
                {data: 'cant'},
                {data: 'cost'},
                {data: 'pvp'},
                {data: 'ganancia'},
            ],
            columnDefs: [
                {
                    targets: [3],
                    class: 'text-center',
                },
                {
                    targets: [4, 5],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '$' + data.toFixed(2);
                    }
                },
                {
                    targets: [6],
                    class: 'text-center',
                    render: function (data, type, row) {
                        var cls = data < 0 ? 'text-danger' : 'text-success';
                        return '<span class="' + cls + ' font-weight-bold">$' + data.toFixed(2) + '</span>';
                    }
                }
            ],
            initComplete: function (settings, json) {
                $(this).wrap('<div class="dataTables_scroll"><div/>');
            }
        });
        $('#myModalDetail').modal('show');
    }
};

$(function () {

    current_date = new moment().format('YYYY-MM-DD');
    input_date_range = $('input[name="date_range"]');

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

    $('.drp-buttons').hide();

    report.initTable();

    report.list(false);

    $('.btnSearchAll').on('click', function () {
        report.list(true);
    });

    $('#tblReport tbody')
        .off()
        .on('click', 'a[rel="detail"]', function () {
            report.listDetail($(this).data('category-id'));
        });
});
