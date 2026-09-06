var input_date_range;
var database_backups = {
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
            columns: [
                {data: "id"},
                {data: "user.username"},
                {data: "date_joined"},
                {data: "hour"},
                {data: "remote_addr"},
                {data: "http_user_agent"},
                {data: "archive"},
                {data: "id"},
                {data: "id"},
            ],
            columnDefs: [
                {
                    targets: [-3],
                    class: 'text-center',
                    render: function (data, type, row) {
                        var buttons = '<span class="badge badge-secondary badge-pill">Sin archivo</span>';
                        if (!$.isEmptyObject(row.archive)) {
                            buttons = '<a href="' + row.archive + '" target="_blank" data-toggle="tooltip" title="Descargar" class="btn btn-primary btn-xs btn-flat"><i class="fas fa-database"></i></a>';
                        }
                        return buttons;
                    }
                },
                {
                    targets: [-2],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (!$.isEmptyObject(row.google_drive_link)) {
                            return '<a href="' + row.google_drive_link + '" target="_blank" data-toggle="tooltip" title="Ver en Google Drive" class="btn btn-success btn-xs btn-flat"><i class="fab fa-google-drive"></i></a>';
                        }
                        if (!$.isEmptyObject(row.google_drive_upload_error)) {
                            var safeMessage = $('<div>').text(row.google_drive_upload_error).html();
                            return '<span data-toggle="tooltip" title="' + safeMessage + '" class="badge badge-danger badge-pill"><i class="fas fa-exclamation-triangle"></i></span>';
                        }
                        return '<span class="text-muted">&mdash;</span>';
                    }
                },
                {
                    targets: [-1],
                    class: 'text-center',
                    render: function (data, type, row) {
                        var buttons = '';
                        if (!$.isEmptyObject(row.archive)) {
                            buttons += '<a href="' + pathname + 'restore/' + row.id + '/" data-toggle="tooltip" title="Restaurar" class="btn btn-warning btn-xs btn-flat"><i class="fas fa-undo"></i></a> ';
                        }
                        buttons += '<a href="' + pathname + 'delete/' + row.id + '/" data-toggle="tooltip" title="Eliminar" class="btn btn-danger btn-xs btn-flat"><i class="fas fa-trash"></i></a>';
                        return buttons;
                    }
                },
            ],
            rowCallback: function (row, data, index) {

            },
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
                startDate: new Date(),
                locale: {
                    format: 'YYYY-MM-DD',
                },
                autoApply: true,
            }
        )
        .on('change.daterangepicker apply.daterangepicker', function (ev, picker) {
            database_backups.list(false);
        });

    $('.drp-buttons').hide();

    $('.btnSearchAll').on('click', function () {
        database_backups.list(true);
    });

    database_backups.list(false);
});