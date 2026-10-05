var tblPeriod;

$(function () {
    tblPeriod = $('#data').DataTable({
        autoWidth: false,
        destroy: true,
        deferRender: true,
        order: [[0, 'desc']],
        ajax: {
            url: pathname,
            type: 'POST',
            headers: {'X-CSRFToken': csrftoken},
            data: {'action': 'search'},
            dataSrc: ''
        },
        columns: [
            {data: 'name'},
            {data: 'status.name'},
            {data: 'closed_at'},
            {data: 'closed_by'},
            {data: 'id'},
        ],
        columnDefs: [
            {
                targets: [1],
                class: 'text-center',
                render: function (data, type, row) {
                    return row.status.id === 'closed' ? '<span class="badge badge-danger">Cerrado</span>' : '<span class="badge badge-success">Abierto</span>';
                }
            },
            {
                targets: [-1],
                class: 'text-center',
                orderable: false,
                render: function (data, type, row) {
                    if (row.status.id === 'closed') {
                        return '<a rel="reopen" class="btn btn-warning btn-xs btn-flat"><i class="fas fa-lock-open"></i> Reabrir</a>';
                    }
                    return '<a rel="close" class="btn btn-danger btn-xs btn-flat"><i class="fas fa-lock"></i> Cerrar</a>';
                }
            },
        ],
        initComplete: function () {
            $(this).wrap('<div class="dataTables_scroll"><div/>');
        }
    });

    $('#data tbody').on('click', 'a[rel="close"], a[rel="reopen"]', function () {
        var action = $(this).attr('rel');
        var row = tblPeriod.row($(this).closest('tr')).data();
        dialog_action({
            'title': action === 'close' ? 'Cerrar período ' + row.name : 'Reabrir período ' + row.name,
            'content': action === 'close'
                ? 'Se bloquearán los asientos del período. ¿Desea continuar?'
                : 'Los asientos del período podrán volver a modificarse. ¿Desea continuar?',
            'success': function () {
                execute_ajax_request({
                    'params': {'action': action, 'id': row.id},
                    'success': function () {
                        tblPeriod.ajax.reload();
                    }
                });
            },
            'cancel': function () {
            }
        });
    });
});
