var tblCombo;
var combo = {
    list: function () {
        tblCombo = $('#data').DataTable({
            autoWidth: false,
            destroy: true,
            deferRender: true,
            ajax: {
                url: pathname,
                type: 'POST',
                headers: {
                    'X-CSRFToken': csrftoken
                },
                data: {
                    'action': 'search'
                },
                dataSrc: ""
            },
            columns: [
                {data: "id"},
                {data: "code"},
                {data: "name"},
                {data: "dscto"},
                {data: "price_current"},
                {data: "price_final"},
                {data: "available_stock"},
                {data: "active"},
                {data: "id"},
            ],
            columnDefs: [
                {
                    targets: [3],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return data.toFixed(2) + '%';
                    }
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
                        if (data === null) {
                            return '<span class="badge badge-secondary badge-pill">Sin límite</span>';
                        }
                        if (data <= 0) {
                            return '<span class="badge badge-danger badge-pill">' + data + '</span>';
                        }
                        return '<span class="badge badge-success badge-pill">' + data + '</span>';
                    }
                },
                {
                    targets: [7],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (data) {
                            return '<span class="badge badge-success badge-pill">Activo</span>';
                        }
                        return '<span class="badge badge-danger badge-pill">Inactivo</span>';
                    }
                },
                {
                    targets: [-1],
                    class: 'text-center',
                    render: function (data, type, row) {
                        var buttons = '<a href="' + pathname + 'update/' + row.id + '/" data-toggle="tooltip" title="Editar" class="btn btn-warning btn-xs btn-flat"><i class="fas fa-edit"></i></a> ';
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
    combo.list();
});
