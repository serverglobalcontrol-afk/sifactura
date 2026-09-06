function formatDateDMY(isoDate) {
    var parts = isoDate.split('-');
    return parts.length === 3 ? parts[2] + '/' + parts[1] + '/' + parts[0] : isoDate;
}

var company = {
    list: function () {
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
                data: {
                    'action': 'search'
                },
                dataSrc: ""
            },
            columns: [
                {"data": "id"},
                {"data": "business_name"},
                {"data": "tradename"},
                {"data": "ruc"},
                {"data": "mobile"},
                {"data": "scheme"},
                {"data": "plan.full_name"},
                {"data": "scheme"},
                {"data": "plan_end_date"},
                {"data": "active"},
                {"data": "id"},
            ],
            columnDefs: [
                {
                    targets: [-6],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (!$.isEmptyObject(row.scheme)) {
                            return row.scheme.name;
                        }
                        return '---';
                    }
                },
                {
                    targets: [-4],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (!$.isEmptyObject(row.scheme) && row.scheme.created_on) {
                            return formatDateDMY(row.scheme.created_on);
                        }
                        return '---';
                    }
                },
                {
                    targets: [-3],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (!data) {
                            return '---';
                        }
                        var label = formatDateDMY(data);
                        if (row.days_until_plan_expires === null || row.days_until_plan_expires === undefined) {
                            return label;
                        }
                        if (row.days_until_plan_expires < 0) {
                            return '<span class="badge badge-pill badge-danger" data-toggle="tooltip" title="Plan vencido">' + label + '</span>';
                        }
                        if (row.days_until_plan_expires <= 30) {
                            return '<span class="badge badge-pill badge-warning" data-toggle="tooltip" title="Vence en ' + row.days_until_plan_expires + ' días">' + label + '</span>';
                        }
                        return label;
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
    company.list();
});