var tblProducts;
var product = {
    list: function () {
        tblProducts = $('#data').DataTable({
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
                {data: "name"},
                {data: "code"},
                {data: "category.name"},
                {data: "inventoried"},
                {data: "image"},
                {data: "barcode"},
                {data: "price"},
                {data: "pvp"},
                {data: "price_promotion"},
                {data: "stock"},
                {data: "stock_minimo"},
                {data: "id"},
            ],
            columnDefs: [
                {
                    targets: [4],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (row.inventoried) {
                            return 'Si';
                        }
                        return 'No';
                    }
                },
                {
                    targets: [5],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '<a rel="image" class="btn btn-secondary btn-xs btn-flat"><i class="fas fa-file-image"></i></a>';
                    }
                },
                {
                    targets: [6],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '<a rel="barcode" class="btn btn-success btn-xs btn-flat"><i class="fas fa-barcode"></i></a>';
                    }
                },
                {
                    targets: [7, 8, 9],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '$' + data.toFixed(2);
                    }
                },
                {
                    targets: [10],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (!row.inventoried) {
                            return '<span class="badge badge-secondary badge-pill">Sin stock</span>';
                        }
                        if (row.stock <= 0) {
                            return '<span class="badge badge-danger badge-pill">' + row.stock + '</span>';
                        }
                        if (row.low_stock) {
                            return '<span class="badge badge-warning badge-pill" data-toggle="tooltip" title="Stock bajo el mínimo configurado">' + row.stock + '</span>';
                        }
                        return '<span class="badge badge-success badge-pill">' + row.stock + '</span>';
                    }
                },
                {
                    targets: [11],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (!row.inventoried) {
                            return '-';
                        }
                        return row.stock_minimo;
                    }
                },
                {
                    targets: [12],
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

$.fn.dataTable.ext.search.push(function (settings, data, dataIndex) {
    if (settings.nTable.id !== 'data' || !$('#chkLowStockOnly').is(':checked')) {
        return true;
    }
    var row = tblProducts.row(dataIndex).data();
    return !!(row && row.low_stock);
});

$(function () {
    product.list();

    $('#data').addClass('table-sm');

    $('#chkLowStockOnly').on('change', function () {
        tblProducts.draw();
    });

    $('#data tbody')
        .off()
        .on('click', 'a[rel="image"]', function () {
            var tr = tblProducts.cell($(this).closest('td, li')).index();
            var data = tblProducts.row(tr.row).data();
            load_image({'url': data.image});
        })
        .on('click', 'a[rel="barcode"]', function () {
            var tr = tblProducts.cell($(this).closest('td, li')).index();
            var data = tblProducts.row(tr.row).data();
            load_image({'url': data.barcode});
        });
})