var input_date_range;
var select_product;
var tblMovements;

var movement = {
    list: function () {
        var parameters = {
            'action': 'search',
            'start_date': input_date_range.data('daterangepicker').startDate.format('YYYY-MM-DD'),
            'end_date': input_date_range.data('daterangepicker').endDate.format('YYYY-MM-DD'),
            'product_id': select_product.val() || '',
        };
        tblMovements = $('#tblMovements').DataTable({
            autoWidth: false,
            destroy: true,
            ajax: {
                url: pathname,
                type: 'POST',
                headers: {
                    'X-CSRFToken': csrftoken
                },
                data: parameters,
                dataSrc: ''
            },
            order: [[0, 'desc']],
            paging: true,
            ordering: true,
            searching: true,
            columns: [
                {data: "date_joined"},
                {data: "product.full_name"},
                {data: "movement_type.name"},
                {data: "direction"},
                {data: "quantity"},
                {data: "stock_before"},
                {data: "stock_after"},
                {data: "reference"},
                {data: "reason"},
                {data: "user"},
            ],
            columnDefs: [
                {
                    targets: [0, 2, 3, 4, 5, 6],
                    class: 'text-center',
                },
                {
                    targets: [3],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (data === 'Entrada') {
                            return '<span class="badge badge-success badge-pill"><i class="fas fa-arrow-down"></i> Entrada</span>';
                        }
                        return '<span class="badge badge-danger badge-pill"><i class="fas fa-arrow-up"></i> Salida</span>';
                    }
                },
                {
                    targets: [4],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return (data > 0 ? '+' : '') + data;
                    }
                },
                {
                    targets: [8],
                    render: function (data, type, row) {
                        return data || '-';
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
    select_product = $('select[name="product"]');

    select_product.select2({
        theme: 'bootstrap4',
        language: 'es',
        allowClear: true,
        placeholder: 'Todos los productos',
        ajax: {
            delay: 250,
            type: 'POST',
            headers: {
                'X-CSRFToken': csrftoken
            },
            url: pathname,
            data: function (params) {
                return {
                    term: params.term || '',
                    action: 'search_product'
                };
            },
            processResults: function (data) {
                return {results: data};
            },
        },
        minimumInputLength: 0,
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

    // Si se llega desde el listado de Productos con "Ver Kardex", se preselecciona
    // ese producto y se amplía el rango de fechas para mostrar todo su historial.
    var urlParams = new URLSearchParams(window.location.search);
    var presetProductId = urlParams.get('product');
    var presetProductText = urlParams.get('text');
    if (presetProductId && presetProductText) {
        var option = new Option(presetProductText, presetProductId, true, true);
        select_product.append(option).trigger('change');
        input_date_range.data('daterangepicker').setStartDate(moment().subtract(2, 'years'));
        input_date_range.data('daterangepicker').setEndDate(moment());
        input_date_range.val(input_date_range.data('daterangepicker').startDate.format('YYYY-MM-DD') + ' - ' + input_date_range.data('daterangepicker').endDate.format('YYYY-MM-DD'));
    }

    movement.list();

    $('.btnSearch').on('click', function () {
        movement.list();
    });
});
