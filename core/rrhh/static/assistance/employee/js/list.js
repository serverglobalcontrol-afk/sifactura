var input_date_range;
var tblAssistance;
var assistance = {
    list: function () {
        var parameters = {
            'action': 'search',
            'start_date': input_date_range.data('daterangepicker').startDate.format('YYYY-MM-DD'),
            'end_date': input_date_range.data('daterangepicker').endDate.format('YYYY-MM-DD'),
        };
        tblAssistance = $('#tblAssistance').DataTable({
            autoWidth: false,
            destroy: true,
            ajax: {
                url: pathname,
                type: 'POST',
                data: parameters,
                dataSrc: "",
                headers: {
                    'X-CSRFToken': csrftoken
                }
            },
            columns: [
                {data: "assistance.date_joined"},
                {data: "employee.user.names"},
                {data: "employee.dni"},
                {data: "employee.position.name"},
                {data: "employee.area.name"},
                {data: "description"},
                {data: "check_in"},
                {data: "check_out"},
                {data: "hours_worked"},
                {data: "overtime_hours"},
                {data: "state"},
            ],
            columnDefs: [
                {
                    targets: [0],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return data;
                    }
                },
                {
                    targets: [5],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (!$.isEmptyObject(row.description)) {
                            return row.description;
                        }
                        return 'Sin detalles';
                    }
                },
                {
                    targets: [6, 7],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return data || '-';
                    }
                },
                {
                    targets: [8, 9],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return data;
                    }
                },
                {
                    targets: [-1],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (row.state) {
                            return '<span class="badge badge-success badge-pill">Si</span>';
                        }
                        return '<span class="badge badge-danger badge-pill">No</span>';
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

    input_date_range
        .daterangepicker({
            language: 'auto',
            startDate: new Date(),
            locale: {
                format: 'YYYY-MM-DD',
            }
        });

    $('.drp-buttons').hide();

    $('.btnSearchAssistances').on('click', function () {
        assistance.list();
    });
});