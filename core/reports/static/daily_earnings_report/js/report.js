var input_date_range;
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
                {data: "units_sold"},
                {data: "revenue"},
                {data: "cost"},
                {data: "profit"},
                {data: "margin"},
            ],
            columnDefs: [
                {
                    targets: [1],
                    class: 'text-center',
                },
                {
                    targets: [2, 3],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '$' + data.toFixed(2);
                    }
                },
                {
                    targets: [4],
                    class: 'text-center',
                    render: function (data, type, row) {
                        var cls = data < 0 ? 'text-danger' : 'text-success';
                        return '<span class="' + cls + ' font-weight-bold">$' + data.toFixed(2) + '</span>';
                    }
                },
                {
                    targets: [5],
                    class: 'text-center',
                    render: function (data, type, row) {
                        var cls = data < 0 ? 'text-danger' : 'text-success';
                        return '<span class="' + cls + '">' + data.toFixed(2) + '%</span>';
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
                var totalUnits = sumColumn('units_sold');
                var totalRevenue = sumColumn('revenue');
                var totalCost = sumColumn('cost');
                var totalProfit = sumColumn('profit');
                var totalMargin = totalRevenue ? (totalProfit / totalRevenue) * 100 : 0;
                $('#footerUnits').html(totalUnits);
                $('#footerRevenue').html('$' + totalRevenue.toFixed(2));
                $('#footerCost').html('$' + totalCost.toFixed(2));
                $('#footerProfit').html('$' + totalProfit.toFixed(2));
                $('#footerMargin').html(totalMargin.toFixed(2) + '%');
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
});
