var input_date_range;
var select_employee;
var tblReport;
var report = {
    getPrintUrl: function () {
        var params = new URLSearchParams({
            'start_date': input_date_range.data('daterangepicker').startDate.format('YYYY-MM-DD'),
            'end_date': input_date_range.data('daterangepicker').endDate.format('YYYY-MM-DD'),
            'employee_id': select_employee.select2('data').map(value => value.id).join(','),
        });
        return pathname + 'print/?' + params.toString();
    },
    initTable: function () {
        tblReport = $('#tblReport').DataTable({
            autoWidth: false,
            destroy: true,
        });
    },
    list: function () {
        var parameters = {
            'action': 'search_report',
            'start_date': input_date_range.data('daterangepicker').startDate.format('YYYY-MM-DD'),
            'end_date': input_date_range.data('daterangepicker').endDate.format('YYYY-MM-DD'),
            'employee_id': JSON.stringify(select_employee.select2('data').map(value => value.id)),
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
            order: [[0, 'asc']],
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
                    text: '<i class="fas fa-file-pdf"></i> Descargar Pdf',
                    titleAttr: 'PDF',
                    className: 'btn btn-danger btn-flat btn-sm',
                    action: function () {
                        window.open(report.getPrintUrl());
                    }
                }
            ],
            columns: [
                {data: "employee.user.names"},
                {data: "days_worked"},
                {data: "regular_hours"},
                {data: "overtime_hours"},
                {data: "total_hours"},
                {data: "hourly_rate"},
                {data: "overtime_value"},
                {data: "total_value"},
            ],
            columnDefs: [
                {
                    targets: [1, 2, 3, 4],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return data;
                    }
                },
                {
                    targets: [5, 6, 7],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '$' + parseFloat(data).toFixed(2);
                    }
                }
            ],
            initComplete: function (settings, json) {
                $(this).wrap('<div class="dataTables_scroll"><div/>');
            }
        });
    }
};

$(function () {

    input_date_range = $('input[name="date_range"]');
    select_employee = $('select[name="employee"]');

    $('.select2').select2({
        placeholder: 'Buscar..',
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

    report.list();

    $('.btnSearch').on('click', function () {
        report.list();
    });
});
