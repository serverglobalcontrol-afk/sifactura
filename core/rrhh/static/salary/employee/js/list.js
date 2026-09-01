var input_year;
var select_month;
var tblSalary;
var salary = {
    model: {},
    list: function () {
        var parameters = {
            'action': 'search',
            'year': input_year.datetimepicker('date').format("YYYY"),
            'month': select_month.val()
        };
        tblSalary = $('#data').DataTable({
            autoWidth: false,
            destroy: true,
            ajax: {
                url: pathname,
                type: 'POST',
                headers: {
                    'X-CSRFToken': csrftoken
                },
                data: parameters,
                dataSrc: "",
                beforeSend: function () {
                    loading({'text': '...'});
                },
                complete: function () {
                    setTimeout(function () {
                        $.LoadingOverlay("hide");
                    }, 750);
                }
            },
            columns: [
                {data: "employee.code"},
                {data: "employee.user.names"},
                {data: "employee.dni"},
                {data: "salary.year"},
                {data: "salary.month.name"},
                {data: "income"},
                {data: "expenses"},
                {data: "total_amount"},
                {data: "id"},
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
                    targets: [-2, -3, -4],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '$' + data;
                    }
                },
                {
                    targets: [-5, -6],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return data;
                    }
                },
                {
                    targets: [-1],
                    class: 'text-center',
                    render: function (data, type, row) {
                        var buttons = '<a class="btn btn-success btn-xs btn-flat" rel="detail" data-toggle="tooltip" title="Detalle"><i class="fas fa-folder-open"></i></a> ';
                        buttons += '<a href="' + pathname + 'print/receipt/' + row.id + '/" target="_blank" data-toggle="tooltip" title="Imprimir" class="btn btn-danger btn-xs btn-flat"><i class="fas fa-file-alt"></i></a>';
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
    input_year = $('input[name="year"]');
    select_month = $('select[name="month"]');

    input_year.datetimepicker({
        viewMode: 'years',
        format: 'YYYY',
        useCurrent: false,
        locale: 'es'
    });

    input_year.on('change.datetimepicker', function (e) {
        salary.list();
    });

    $('.btnSearch').on('click', function () {
        salary.list();
    });

    $('#data tbody')
        .off()
        .on('click', 'a[rel="detail"]', function () {
            $('.tooltip').remove();
            var tr = tblSalary.cell($(this).closest('td, li')).index(),
                row = tblSalary.row(tr.row).data();
            salary.model = row;
            $('#tblHeadings').DataTable({
                autoWidth: false,
                destroy: true,
                ajax: {
                    url: pathname,
                    type: 'POST',
                    headers: {
                        'X-CSRFToken': csrftoken
                    },
                    data: {
                        'action': 'search_detail_headings',
                        'id': row.id
                    },
                    dataSrc: ""
                },
                ordering: false,
                lengthChange: false,
                searching: false,
                paginate: false,
                columnDefs: [
                    {
                        targets: [0],
                        class: 'text-left',
                        render: function (data, type, row) {
                            return data.toUpperCase();
                        }
                    },
                    {
                        targets: [1],
                        class: 'text-center',
                        render: function (data, type, row) {
                            return data;
                        }
                    },
                    {
                        targets: [-1, -2],
                        class: 'text-center',
                        render: function (data, type, row) {
                            if (data === '---') {
                                return data;
                            }
                            return '$' + data
                        }
                    },
                ],
                initComplete: function (settings, json) {
                    $(this).wrap('<div class="dataTables_scroll"><div/>');
                }
            });
            $('#myModalSalary').modal('show');
        });

    $('.select2').select2({
        theme: 'bootstrap4',
        language: "es"
    });

    select_month.on('change', function () {
        salary.list();
    });

    $('.btnPrintReceiptEmployee').on('click', function () {
        var url = pathname + 'print/receipt/' + salary.model.id + '/';
        window.open(url, '_blank').focus();
    });
});