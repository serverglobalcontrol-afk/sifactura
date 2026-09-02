var input_date_range;
var select_employee;
var tblReport;
var report = {
    getPrintUrl: function () {
        var employeeId = select_employee.val();
        if (!employeeId) {
            return null;
        }
        var params = new URLSearchParams({
            'start_date': input_date_range.data('daterangepicker').startDate.format('YYYY-MM-DD'),
            'end_date': input_date_range.data('daterangepicker').endDate.format('YYYY-MM-DD'),
            'employee_id': employeeId,
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
        var employeeId = select_employee.val();
        if (!employeeId) {
            message_error('Debe seleccionar un empleado');
            return false;
        }
        var parameters = {
            'action': 'search_report',
            'start_date': input_date_range.data('daterangepicker').startDate.format('YYYY-MM-DD'),
            'end_date': input_date_range.data('daterangepicker').endDate.format('YYYY-MM-DD'),
            'employee_id': employeeId,
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
                        var url = report.getPrintUrl();
                        if (url) {
                            window.open(url);
                        }
                    }
                }
            ],
            columns: [
                {data: "date_joined"},
                {data: "state"},
                {data: "scheduled_check_in"},
                {data: "check_in"},
                {data: "late_minutes"},
                {data: "scheduled_check_out"},
                {data: "check_out"},
                {data: "early_departure_minutes"},
                {data: "hours_worked"},
                {data: "overtime_hours"},
            ],
            columnDefs: [
                {
                    targets: [1],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (row.state) {
                            return '<span class="badge badge-success badge-pill">Si</span>';
                        }
                        return '<span class="badge badge-danger badge-pill">No</span>';
                    }
                },
                {
                    targets: [2, 3, 5, 6],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return data || '-';
                    }
                },
                {
                    targets: [4],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (data > 0) {
                            return '<span class="text-warning font-weight-bold">' + data + ' min</span>';
                        }
                        return '-';
                    }
                },
                {
                    targets: [7],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (data > 0) {
                            return '<span class="text-warning font-weight-bold">' + data + ' min</span>';
                        }
                        return '-';
                    }
                },
                {
                    targets: [8, 9],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return data;
                    }
                },
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
        placeholder: 'Seleccione un empleado',
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
});
