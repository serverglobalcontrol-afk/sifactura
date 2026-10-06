// Reportes contables: cada plantilla define window.REPORT = {
//   columns: [{data: ..., money: true|false, align: 'text-right'}...],
//   totals: [índices de columnas que suman en el pie],
//   extra: function () { return {parámetros adicionales}; }
// } antes de cargar este archivo.
var tblReport;

function money_format(value) {
    return '$' + (parseFloat(value) || 0).toFixed(2);
}

function run_report() {
    var parameters = {
        'action': 'search_report',
        'start_date': $('#startDate').val(),
        'end_date': $('#endDate').val(),
    };
    if (window.REPORT.extra) {
        $.extend(parameters, window.REPORT.extra());
    }
    var cfg = window.REPORT;
    var widths = cfg.columns.map(function () {
        return '*';
    });
    var moneyTargets = [];
    cfg.columns.forEach(function (c, i) {
        if (c.money) {
            moneyTargets.push(i);
        }
    });
    tblReport = $('#tblReport').DataTable({
        destroy: true,
        autoWidth: false,
        ajax: {
            url: pathname,
            type: 'POST',
            headers: {'X-CSRFToken': csrftoken},
            data: parameters,
            dataSrc: ''
        },
        paging: false,
        ordering: false,
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
                    apply_report_pdf_layout(doc, widths);
                }
            }
        ],
        columns: cfg.columns.map(function (c) {
            var column = {data: c.data};
            if (c.render) {
                column.render = c.render;
            }
            return column;
        }),
        createdRow: function (row, data) {
            if (cfg.rowClass) {
                $(row).addClass(cfg.rowClass(data));
            }
        },
        columnDefs: [
            {
                targets: moneyTargets,
                class: 'text-right',
                render: function (data) {
                    return money_format(data);
                }
            }
        ],
        footerCallback: function () {
            if (!cfg.totals) {
                return;
            }
            var api = this.api();
            cfg.totals.forEach(function (index) {
                var sum = api.column(index).data().reduce(function (a, b) {
                    return a + (parseFloat(b) || 0);
                }, 0);
                $(api.column(index).footer()).html(money_format(sum));
            });
        },
    });
}

$(function () {
    run_report();
    $('#btnSearch').on('click', run_report);
});
