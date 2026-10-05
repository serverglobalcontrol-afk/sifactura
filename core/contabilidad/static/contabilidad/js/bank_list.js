$(function () {
    $('#data').DataTable({
        autoWidth: false,
        destroy: true,
        deferRender: true,
        ajax: {
            url: pathname,
            type: 'POST',
            headers: {'X-CSRFToken': csrftoken},
            data: {'action': 'search'},
            dataSrc: ''
        },
        columns: [
            {data: 'bank_name'},
            {data: 'number'},
            {data: 'account_type.name'},
            {data: 'holder'},
            {data: 'account'},
            {data: 'active'},
            {data: 'id'},
        ],
        columnDefs: [
            {
                targets: [-2],
                class: 'text-center',
                render: function (data) {
                    return data ? '<span class="badge badge-success">Activa</span>' : '<span class="badge badge-danger">Inactiva</span>';
                }
            },
            {
                targets: [-1],
                class: 'text-center',
                orderable: false,
                render: function (data, type, row) {
                    var buttons = '<a href="' + pathname + 'update/' + row.id + '/" data-toggle="tooltip" title="Editar" class="btn btn-warning btn-xs btn-flat"><i class="fas fa-edit"></i></a> ';
                    buttons += '<a href="' + pathname + 'delete/' + row.id + '/" data-toggle="tooltip" title="Eliminar" class="btn btn-danger btn-xs btn-flat"><i class="fas fa-trash"></i></a>';
                    return buttons;
                }
            },
        ],
        initComplete: function () {
            $('[data-toggle="tooltip"]').tooltip();
            $(this).wrap('<div class="dataTables_scroll"><div/>');
        }
    });
});
