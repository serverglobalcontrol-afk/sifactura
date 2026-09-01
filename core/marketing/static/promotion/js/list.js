var tblPromotions;
var promotion = {
    list: function () {
        tblPromotions = $('#data').DataTable({
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
                {"data": "id"},
                {"data": "image"},
                {"data": "title"},
                {"data": "description"},
                {"data": "order"},
                {"data": "active"},
                {"data": "id"},
            ],
            columnDefs: [
                {
                    targets: [-6],
                    class: 'text-center',
                    orderable: false,
                    render: function (data, type, row) {
                        return '<a rel="image" class="btn btn-secondary btn-xs btn-flat"><i class="fas fa-file-image"></i></a>';
                    }
                },
                {
                    targets: [-2],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (data) {
                            return '<span class="badge badge-pill badge-success">Activo</span>';
                        }
                        return '<span class="badge badge-pill badge-danger">Inactivo</span>';
                    }
                },
                {
                    targets: [-1],
                    class: 'text-center',
                    orderable: false,
                    render: function (data, type, row) {
                        var buttons = '<a href="' + pathname + 'update/' + row.id + '/" data-toggle="tooltip" title="Editar" class="btn btn-warning btn-xs btn-flat"><i class="fas fa-edit"></i></a> ';
                        buttons += '<a href="' + pathname + 'delete/' + row.id + '/" data-toggle="tooltip" title="Eliminar" class="btn btn-danger btn-xs btn-flat"><i class="fas fa-trash-alt"></i></a>';
                        return buttons;
                    }
                },
            ],
            initComplete: function (settings, json) {
                $('[data-toggle="tooltip"]').tooltip();
                $(this).wrap('<div class="dataTables_scroll"><div/>');
            }
        });
    }
};

$(function () {
    promotion.list();

    $('#data tbody')
        .off()
        .on('click', 'a[rel="image"]', function () {
            var tr = tblPromotions.cell($(this).closest('td, li')).index();
            var data = tblPromotions.row(tr.row).data();
            load_image({'url': data.image});
        });
});
