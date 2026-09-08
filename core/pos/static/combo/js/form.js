var fv;
var tblProducts, tblSearchProducts;
var input_search_product;

var combo = {
    detail: {
        products: [],
    },
    listProducts: function () {
        tblProducts = $('#tblProducts').DataTable({
            autoWidth: false,
            destroy: true,
            data: this.detail.products,
            ordering: false,
            lengthChange: false,
            searching: false,
            paginate: false,
            columns: [
                {data: "id"},
                {data: "code"},
                {data: "full_name"},
                {data: "stock"},
                {data: "pvp"},
                {data: "cant"},
                {data: "id"},
            ],
            columnDefs: [
                {
                    targets: [-4],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (row.inventoried) {
                            if (row.stock > 0) {
                                return '<span class="badge badge-success badge-pill">' + row.stock + '</span>';
                            }
                            return '<span class="badge badge-danger badge-pill">' + row.stock + '</span>';
                        }
                        return '<span class="badge badge-secondary badge-pill">Sin stock</span>';
                    }
                },
                {
                    targets: [-3],
                    class: 'text-right',
                    render: function (data, type, row) {
                        return '$' + parseFloat(row.pvp).toFixed(2);
                    }
                },
                {
                    targets: [-2],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '<input type="text" class="form-control" autocomplete="off" name="cant" value="' + row.cant + '">';
                    }
                },
                {
                    targets: [-1],
                    class: 'text-right',
                    render: function (data, type, row) {
                        return '$' + (parseFloat(row.pvp) * parseInt(row.cant)).toFixed(2);
                    }
                },
                {
                    targets: [0],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '<a rel="remove" class="btn btn-danger btn-flat btn-xs"><i class="fas fa-times"></i></a>';
                    }
                },
            ],
            rowCallback: function (row, data, index) {
                var tr = $(row).closest('tr');
                tr.find('input[name="cant"]')
                    .TouchSpin({
                        min: 1,
                        max: 1000000
                    })
                    .on('keypress', function (e) {
                        return validate_text_box({'event': e, 'type': 'numbers'});
                    });
            },
            initComplete: function (settings, json) {
                $(this).wrap('<div class="dataTables_scroll"><div/>');
            }
        });
        this.calculateTotals();
    },
    getProductsIds: function () {
        return this.detail.products.map(value => value.id);
    },
    addProduct: function (item) {
        if (!item.cant) item.cant = 1;
        this.detail.products.push(item);
        this.listProducts();
    },
    // Igual que el resumen de una factura: suma el precio de referencia
    // (pvp) de cada componente por su cantidad, aplica el descuento único
    // del combo sobre ese subtotal, y calcula el total resultante. Es
    // referencial -el precio real de venta se recalcula en la venta a
    // partir del precio vigente de cada producto en ese momento.
    calculateTotals: function () {
        var subtotal = this.detail.products.reduce(function (acc, item) {
            return acc + (parseFloat(item.pvp) * parseInt(item.cant));
        }, 0);
        var dscto = parseFloat($('input[name="dscto"]').val()) || 0;
        var total_dscto = subtotal * (dscto / 100);
        var total = subtotal - total_dscto;
        $('#txtSubtotal').text('$' + subtotal.toFixed(2));
        $('#txtTotalDscto').text('$' + total_dscto.toFixed(2));
        $('#txtTotal').text('$' + total.toFixed(2));
    },
};

document.addEventListener('DOMContentLoaded', function (e) {
    fv = FormValidation.formValidation(document.getElementById('frmForm'), {
            locale: 'es_ES',
            localization: FormValidation.locales.es_ES,
            plugins: {
                trigger: new FormValidation.plugins.Trigger(),
                submitButton: new FormValidation.plugins.SubmitButton(),
                bootstrap: new FormValidation.plugins.Bootstrap(),
                icon: new FormValidation.plugins.Icon({
                    valid: 'fa fa-check',
                    invalid: 'fa fa-times',
                    validating: 'fa fa-refresh',
                }),
            },
            fields: {
                code: {
                    validators: {
                        notEmpty: {},
                    }
                },
                name: {
                    validators: {
                        notEmpty: {},
                    }
                },
            },
        }
    )
        .on('core.element.validated', function (e) {
            if (e.valid) {
                const groupEle = FormValidation.utils.closest(e.element, '.form-group');
                if (groupEle) {
                    FormValidation.utils.classSet(groupEle, {
                        'has-success': false,
                    });
                }
                FormValidation.utils.classSet(e.element, {
                    'is-valid': false,
                });
            }
            const iconPlugin = fv.getPlugin('icon');
            const iconElement = iconPlugin && iconPlugin.icons.has(e.element) ? iconPlugin.icons.get(e.element) : null;
            iconElement && (iconElement.style.display = 'none');
        })
        .on('core.validator.validated', function (e) {
            if (!e.result.valid) {
                const messages = [].slice.call(fv.form.querySelectorAll('[data-field="' + e.field + '"][data-validator]'));
                messages.forEach((messageEle) => {
                    const validator = messageEle.getAttribute('data-validator');
                    messageEle.style.display = validator === e.validator ? 'block' : 'none';
                });
            }
        })
        .on('core.form.valid', function () {
            if (combo.detail.products.length === 0) {
                message_error('Debe tener al menos un producto componente en el detalle');
                return false;
            }
            var params = new FormData(fv.form);
            params.append('products', JSON.stringify(combo.detail.products));
            var args = {
                'params': params,
                'form': fv.form
            };
            submit_with_formdata(args);
        });
});

$(function () {

    input_search_product = $('input[name="search_product"]');

    // Products

    input_search_product.autocomplete({
        source: function (request, response) {
            $.ajax({
                url: pathname,
                data: {
                    'action': 'search_product',
                    'term': request.term,
                    'ids': JSON.stringify(combo.getProductsIds()),
                },
                dataType: "json",
                type: "POST",
                headers: {
                    'X-CSRFToken': csrftoken
                },
                beforeSend: function () {

                },
                success: function (data) {
                    response(data);
                }
            });
        },
        min_length: 3,
        delay: 300,
        select: function (event, ui) {
            event.preventDefault();
            $(this).blur();
            ui.item.cant = 1;
            combo.addProduct(ui.item);
            $(this).val('').focus();
        }
    });

    $('.btnClearProducts').on('click', function () {
        input_search_product.val('').focus();
    });

    $('#tblProducts tbody')
        .off()
        .on('change', 'input[name="cant"]', function () {
            var tr = tblProducts.cell($(this).closest('td, li')).index();
            combo.detail.products[tr.row].cant = parseInt($(this).val());
            combo.listProducts();
        })
        .on('click', 'a[rel="remove"]', function () {
            var tr = tblProducts.cell($(this).closest('td, li')).index();
            combo.detail.products.splice(tr.row, 1);
            tblProducts.row(tr.row).remove().draw();
            combo.calculateTotals();
            $('.tooltip').remove();
        });

    $('.btnSearchProducts').on('click', function () {
        tblSearchProducts = $('#tblSearchProducts').DataTable({
            autoWidth: false,
            destroy: true,
            ajax: {
                url: pathname,
                type: 'POST',
                headers: {
                    'X-CSRFToken': csrftoken
                },
                data: {
                    'action': 'search_product',
                    'term': input_search_product.val(),
                    'ids': JSON.stringify(combo.getProductsIds()),
                },
                dataSrc: ""
            },
            columns: [
                {data: "code"},
                {data: "full_name"},
                {data: "stock"},
                {data: "id"},
            ],
            columnDefs: [
                {
                    targets: [-2],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (row.inventoried) {
                            if (row.stock > 0) {
                                return '<span class="badge badge-success badge-pill">' + row.stock + '</span>';
                            }
                            return '<span class="badge badge-danger badge-pill">' + row.stock + '</span>';
                        }
                        return '<span class="badge badge-secondary badge-pill">Sin stock</span>';
                    }
                },
                {
                    targets: [-1],
                    class: 'text-center',
                    render: function (data, type, row) {
                        var content = '<div class="checkbox">';
                        content += '<label><input type="checkbox" class="form-control-checkbox" name="choose" value=""></label>';
                        content += '</div>';
                        return content;
                    }
                }
            ],
            initComplete: function (settings, json) {
                $(this).wrap('<div class="dataTables_scroll"><div/>');
            }
        });
        $('input[name="chooseallproducts"]').prop('checked', false);
        $('#myModalSearchProducts').modal('show');
    });

    $('#myModalSearchProducts').on('hide.bs.modal', function () {
        var products = tblSearchProducts.rows().data().toArray().filter(function (item, key) {
            return item.choose;
        });
        products.forEach(function (value, index, array) {
            value.cant = 1;
            combo.detail.products.push(value);
        });
        combo.listProducts();
    })

    $('#tblSearchProducts tbody')
        .off()
        .on('change', 'input[name="choose"]', function () {
            var row = tblSearchProducts.row($(this).parents('tr')).data();
            row.choose = this.checked;
        });

    $('.btnRemoveAllProducts').on('click', function () {
        if (combo.detail.products.length === 0) return false;
        dialog_action({
            'content': '¿Estas seguro de eliminar todos los items de tu detalle?',
            'success': function () {
                combo.detail.products = [];
                combo.listProducts();
            },
            'cancel': function () {

            }
        });
    });

    $('input[name="chooseallproducts"]')
        .on('change', function () {
            var state = this.checked;
            var cells = tblSearchProducts.cells().nodes();
            $(cells).find('input[name="choose"]').prop('checked', state).change();
            tblSearchProducts.rows().data().toArray().forEach(function (value, index, array) {
                value.choose = state;
            });
        });

    $('input[name="dscto"]')
        .TouchSpin({
            min: 0.00,
            max: 100,
            step: 0.01,
            decimals: 2,
            boostat: 5,
            prefix: '%',
            maxboostedstep: 10
        })
        .on('keypress', function (e) {
            return validate_text_box({'event': e, 'type': 'decimals'});
        })
        .on('change', function () {
            combo.calculateTotals();
        });

    $('i[data-field="input_search_product"]').hide();
});
