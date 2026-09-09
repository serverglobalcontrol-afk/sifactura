var fv;
var select_client;
var input_search_product, input_date_joined;
var tblProducts, tblSearchProducts;

// Etiqueta legible del tipo de precio para el campo de solo lectura -no se
// imprime en la cotización ni en la factura. Valor por defecto; create.html
// lo sobreescribe con los nombres configurados en Bodega > Tipos de Precio.
var CUSTOMER_TYPE_LABELS = {
    retail: 'Público',
    wholesale: 'Distribuidor',
    credit_card: 'Tarjeta de Crédito',
};

function updateCustomerType() {
    var type = quotation.customer && quotation.customer.customer_type ? quotation.customer.customer_type : 'retail';
    $('#txtCustomerType').val(CUSTOMER_TYPE_LABELS[type] || 'Público');
}

var quotation = {
    customer: null,
    detail: {
        subtotal_0: 0.00,
        subtotal_12: 0.00,
        subtotal: 0.00,
        iva: 0.00,
        total_iva: 0.00,
        total_dscto: 0.00,
        total: 0.00,
        products: [],
    },
    addProduct: function (item) {
        var index = this.detail.products.findIndex(value => value.code === item.code);
        if (index === -1) {
            this.detail.products.push(item);
        } else {
            var product = this.detail.products[index];
            product.cant += 1;
        }
        this.listProducts();
    },
    getProductId: function () {
        return this.detail.products.map(value => value.id);
    },
    // Igual que en Sale: un Combo no agrega un tipo de línea nuevo, se
    // expande de inmediato en una línea de producto normal por cada
    // componente (cant = cantidad de combos x cantidad requerida del
    // componente), con el descuento del combo ya aplicado como "dscto" de
    // esa línea.
    addCombo: function (combo, qty) {
        qty = parseInt(qty) || 0;
        if (qty <= 0) {
            message_error('La cantidad de combos debe ser mayor a 0');
            return false;
        }
        if (!combo.components || combo.components.length === 0) {
            message_error('Este combo no tiene productos componentes configurados');
            return false;
        }
        var self = this;
        for (var i = 0; i < combo.components.length; i++) {
            var comp = combo.components[i];
            var needed = qty * comp.cant;
            var already_in_cart = self.detail.products.filter(value => value.id === comp.id).reduce((a, b) => a + (parseInt(b.cant) || 0), 0);
            if (comp.inventoried && comp.stock < (needed + already_in_cart)) {
                message_error('Stock insuficiente de "' + comp.name + '" para agregar ' + qty + ' combo(s) de "' + combo.name + '" (disponible: ' + comp.stock + ', se requieren: ' + (needed + already_in_cart) + ')');
                return false;
            }
        }
        // El precio que se cobra es el que el usuario fijó en el combo
        // (Distribuidor/Público/Tarjeta), repartido proporcionalmente entre
        // los componentes según su peso en el costo de referencia -igual
        // que en Sale.addCombo- para que la suma de las líneas sea
        // exactamente combo.price_final x la cantidad de combos.
        var componentsCost = combo.components.reduce(function (acc, comp) {
            return acc + (comp.price_current * comp.cant);
        }, 0);
        combo.components.forEach(function (comp) {
            var weight = componentsCost > 0 ? (comp.price_current * comp.cant) / componentsCost : (1 / combo.components.length);
            var allocatedListTotal = weight * combo.price_current;
            var unitPrice = comp.cant > 0 ? Math.round((allocatedListTotal / comp.cant) * 100) / 100 : 0;
            self.detail.products.push({
                id: comp.id,
                code: comp.code,
                name: comp.name,
                full_name: comp.full_name,
                stock: comp.stock,
                inventoried: comp.inventoried,
                with_tax: comp.with_tax,
                cant: qty * comp.cant,
                price_current: unitPrice,
                dscto: combo.dscto,
                combo_origin: combo.full_name,
            });
        });
        this.listProducts();
        return true;
    },
    listProducts: function () {
        this.calculateInvoice();
        console.clear();
        console.log(this.detail);
        tblProducts = $('#tblProducts').DataTable({
            autoWidth: false,
            destroy: true,
            data: this.detail.products,
            // ordering: false,
            lengthChange: false,
            searching: false,
            paginate: false,
            columns: [
                {data: "id"},
                {data: "code"},
                {data: "name"},
                {data: "stock"},
                {data: "cant"},
                {data: "price_current"},
                {data: "total_dscto"},
                {data: "total"},
            ],
            columnDefs: [
                {
                    targets: [-5],
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
                    targets: [-4],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '<input type="text" class="form-control" autocomplete="off" name="cant" value="' + row.cant + '">';
                    }
                },
                {
                    targets: [-3],
                    class: 'text-center',
                    render: function (data, type, row) {
                        // Igual que en Sale: solo editable si el producto tiene
                        // marcada "Precio de venta manual" y no viene de un combo.
                        if (row.manual_price && !row.combo_origin) {
                            return '<input type="text" class="form-control" autocomplete="off" name="price_current" value="' + row.price_current + '">';
                        }
                        return '$' + parseFloat(row.price_current).toFixed(2);
                    }
                },
                {
                    targets: [-2],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '<input type="text" class="form-control" autocomplete="off" name="dscto_unitary" value="' + row.dscto + '">';
                    }
                },
                {
                    targets: [-1],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '$' + data.toFixed(2);
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
                var stock = data.inventoried ? data.stock : 1000000;
                tr.find('input[name="cant"]')
                    .TouchSpin({
                        min: 1,
                        max: stock
                    })
                    .on('keypress', function (e) {
                        return validate_text_box({'event': e, 'type': 'numbers'});
                    });

                if (tr.find('input[name="price_current"]').length) {
                    tr.find('input[name="price_current"]').TouchSpin({
                        min: 0.01,
                        max: 1000000,
                        step: 0.01,
                        decimals: 2,
                        boostat: 5,
                        maxboostedstep: 10
                    })
                        .on('keypress', function (e) {
                            return validate_text_box({'event': e, 'type': 'decimals'});
                        });
                }

                tr.find('input[name="dscto_unitary"]')
                    .TouchSpin({
                        min: 0.00,
                        max: 100,
                        step: 0.01,
                        decimals: 2,
                        boostat: 5,
                        maxboostedstep: 10,
                        postfix: "0.00"
                    })
                    .on('keypress', function (e) {
                        return validate_text_box({'event': e, 'type': 'decimals'});
                    });
            },
            initComplete: function (settings, json) {
                $(this).wrap('<div class="dataTables_scroll"><div/>');
            }
        });
    },
    calculateInvoice: function () {
        const round = (num) => Math.round(num * 100) / 100;
        var tax = this.detail.iva / 100;
        this.detail.products.forEach(function (value) {
            const taxRate = parseFloat(tax);
            const discountRate = parseFloat(value.dscto / 100);

            value.iva = taxRate;

            value.price_with_vat = round(value.price_current * (1 + taxRate));
            value.subtotal = value.price_current * value.cant;
            value.total_dscto = value.subtotal * discountRate;

            value.total_iva = round((value.subtotal - value.total_dscto) * taxRate);
            value.total = round(value.subtotal - value.total_dscto);
        });

        this.detail.subtotal_0 = this.detail.products.filter(value => !value.with_tax).reduce((a, b) => a + (parseFloat(b.total) || 0), 0);
        this.detail.subtotal_12 = this.detail.products.filter(value => value.with_tax).reduce((a, b) => a + (parseFloat(b.total) || 0), 0);
        this.detail.total_dscto = this.detail.products.reduce((a, b) => a + (parseFloat(b.total_dscto) || 0), 0);
        this.detail.total_iva = round(this.detail.products.filter(value => value.with_tax).reduce((a, b) => a + (parseFloat(b.total_iva) || 0), 0));
        this.detail.subtotal = round(this.detail.subtotal_0 + this.detail.subtotal_12);
        this.detail.total = round(this.detail.subtotal + this.detail.total_iva);

        $('input[name="subtotal_0"]').val(this.detail.subtotal_0.toFixed(2));
        $('input[name="subtotal_12"]').val(this.detail.subtotal_12.toFixed(2));
        $('input[name="iva"]').val(this.detail.iva.toFixed(2));
        $('input[name="total_iva"]').val(this.detail.total_iva.toFixed(2));
        $('input[name="total_dscto"]').val(this.detail.total_dscto.toFixed(2));
        $('input[name="total"]').val(this.detail.total.toFixed(2));
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
                // excluded: new FormValidation.plugins.Excluded(),
                icon: new FormValidation.plugins.Icon({
                    valid: 'fa fa-check',
                    invalid: 'fa fa-times',
                    validating: 'fa fa-refresh',
                }),
            },
            fields: {
                client: {
                    validators: {
                        notEmpty: {
                            message: 'Seleccione un cliente'
                        }
                    }
                },
                date_joined: {
                    validators: {
                        notEmpty: {
                            enabled: false,
                            message: 'La fecha es obligatoria'
                        },
                        date: {
                            format: 'YYYY-MM-DD',
                            message: 'La fecha no es válida'
                        }
                    }
                }
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
            if (quotation.detail.products.length === 0) {
                return message_error('Debe tener al menos un item en el detalle de la venta');
            }
            var href_url = $(fv.form).attr('data-url');
            var params = new FormData(fv.form);
            params.append('products', JSON.stringify(quotation.detail.products));
            var args = {
                'params': params,
                'success': function (request) {
                    dialog_action({
                        'content': '¿Desea Imprimir la proforma?',
                        'success': function () {
                            window.open(request.print_url, '_blank');
                            location.href = href_url;
                        },
                        'cancel': function () {
                            location.href = href_url;
                        }
                    });
                }
            };
            submit_with_formdata(args);
        });
});

$(function () {
    select_client = $('select[name="client"]');
    input_search_product = $('input[name="search"]');
    input_date_joined = $('input[name="date_joined"]');

    $('.select2').select2({
        theme: 'bootstrap4',
        language: 'es',
    });

    // Customer

    select_client.select2({
        theme: 'bootstrap4',
        language: 'es',
        allowClear: true,
        width: '100%',
        ajax: {
            delay: 250,
            type: 'POST',
            headers: {
                'X-CSRFToken': csrftoken
            },
            url: pathname,
            data: function (params) {
                return {
                    term: params.term,
                    action: 'search_client'
                };
            },
            processResults: function (data) {
                return {
                    results: data
                };
            },
        },
        placeholder: 'Ingrese un nombre o número de cedula de un cliente',
        minimumInputLength: 1,
    })
        .on('select2:select', function (e) {
            quotation.customer = e.params.data;
            fv.revalidateField('client');
            updateCustomerType();
        })
        .on('select2:clear', function (e) {
            quotation.customer = null;
            fv.revalidateField('client');
            updateCustomerType();
        });

    // quotation

    input_date_joined.datetimepicker({
        useCurrent: false,
        format: 'YYYY-MM-DD',
        locale: 'es',
        keepOpen: false,
    });

    input_date_joined.on('change.datetimepicker', function (e) {
        fv.revalidateField('date_joined');
    });

    $('i[data-field="client"]').hide();
    $('i[data-field="input_search_product"]').hide();

    // Product

    input_search_product.autocomplete({
        source: function (request, response) {
            $.ajax({
                url: pathname,
                data: {
                    'action': 'search_product',
                    'term': request.term,
                    'product_id': JSON.stringify(quotation.getProductId()),
                    'customer_type': quotation.customer.customer_type ?? 'retail',
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
            quotation.addProduct(ui.item);
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
            quotation.detail.products[tr.row].cant = parseInt($(this).val());
            quotation.calculateInvoice();
            $('td:last', tblProducts.row(tr.row).node()).html('$' + quotation.detail.products[tr.row].total.toFixed(2));
        })
        .on('change', 'input[name="price_current"]', function () {
            var tr = tblProducts.cell($(this).closest('td, li')).index();
            quotation.detail.products[tr.row].price_current = parseFloat($(this).val());
            quotation.calculateInvoice();
            $('td:last', tblProducts.row(tr.row).node()).html('$' + quotation.detail.products[tr.row].total.toFixed(2));
        })
        .on('change', 'input[name="dscto_unitary"]', function () {
            var tr = tblProducts.cell($(this).closest('td, li')).index();
            quotation.detail.products[tr.row].dscto = parseFloat($(this).val());
            quotation.calculateInvoice();
            var parent = $(this).closest('.bootstrap-touchspin');
            parent.find('.bootstrap-touchspin-postfix').children().html(quotation.detail.products[tr.row].total_dscto.toFixed(2));
            $('td:last', tblProducts.row(tr.row).node()).html('$' + quotation.detail.products[tr.row].total.toFixed(2));
        })
        .on('click', 'a[rel="remove"]', function () {
            var tr = tblProducts.cell($(this).closest('td, li')).index();
            quotation.detail.products.splice(tr.row, 1);
            tblProducts.row(tr.row).remove().draw();
            quotation.calculateInvoice();
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
                    'product_id': JSON.stringify(quotation.getProductId()),
                },
                dataSrc: ""
            },
            columns: [
                {data: "code"},
                {data: "short_name"},
                {data: "pvp"},
                {data: "price_promotion"},
                {data: "stock"},
                {data: "id"},
            ],
            columnDefs: [
                {
                    targets: [-3, -4],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '$' + data.toFixed(4);
                    }
                },
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
                        return '<a rel="add" class="btn btn-success btn-xs btn-flat"><i class="fas fa-plus"></i></a>';
                    }
                }
            ],
            rowCallback: function (row, data, index) {

            },
            initComplete: function (settings, json) {
                $(this).wrap('<div class="dataTables_scroll"><div/>');
            }
        });
        $('#myModalSearchProducts').modal('show');
    });

    $('#tblSearchProducts tbody')
        .off()
        .on('click', 'a[rel="add"]', function () {
            var row = tblSearchProducts.row($(this).parents('tr')).data();
            row.cant = 1;
            quotation.addProduct(row);
            tblSearchProducts.row($(this).parents('tr')).remove().draw();
        });

    $('.btnRemoveAllProducts').on('click', function () {
        if (quotation.detail.products.length === 0) return false;
        dialog_action({
            'content': '¿Estas seguro de eliminar todos los items de tu detalle?',
            'success': function () {
                quotation.detail.products = [];
                quotation.listProducts();
            },
            'cancel': function () {

            }
        });
    });

    // Combos

    var tblSearchCombos;
    $('.btnSearchCombos').on('click', function () {
        tblSearchCombos = $('#tblSearchCombos').DataTable({
            autoWidth: false,
            destroy: true,
            ajax: {
                url: pathname,
                type: 'POST',
                headers: {
                    'X-CSRFToken': csrftoken
                },
                data: {
                    'action': 'search_combo',
                    'customer_type': quotation.customer.customer_type ?? 'retail',
                    'term': ''
                },
                dataSrc: ""
            },
            columns: [
                {data: "code"},
                {data: "name"},
                {data: "dscto"},
                {data: "price_final"},
                {data: "available_stock"},
                {data: "id"},
                {data: "id"},
            ],
            columnDefs: [
                {
                    targets: [2],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return data.toFixed(2) + '%';
                    }
                },
                {
                    targets: [3],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '$' + data.toFixed(2);
                    }
                },
                {
                    targets: [4],
                    class: 'text-center',
                    render: function (data, type, row) {
                        if (row.available_stock === null) {
                            return '<span class="badge badge-secondary badge-pill">Sin límite</span>';
                        }
                        if (row.available_stock <= 0) {
                            return '<span class="badge badge-danger badge-pill">' + row.available_stock + '</span>';
                        }
                        return '<span class="badge badge-success badge-pill">' + row.available_stock + '</span>';
                    }
                },
                {
                    targets: [-2],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '<input type="text" class="form-control" autocomplete="off" name="combo_qty" value="1">';
                    }
                },
                {
                    targets: [-1],
                    class: 'text-center',
                    render: function (data, type, row) {
                        return '<a rel="add" class="btn btn-success btn-flat btn-xs"><i class="fas fa-plus"></i></a>';
                    }
                }
            ],
            rowCallback: function (row, data, index) {
                $(row).find('input[name="combo_qty"]').TouchSpin({
                    min: 1,
                    max: data.available_stock === null ? 1000000 : Math.max(data.available_stock, 1)
                }).on('keypress', function (e) {
                    return validate_text_box({'event': e, 'type': 'numbers'});
                });
            },
            initComplete: function (settings, json) {
                $(this).wrap('<div class="dataTables_scroll"><div/>');
            }
        });
        $('#myModalSearchCombos').modal('show');
    });

    $('#tblSearchCombos tbody')
        .off()
        .on('click', 'a[rel="add"]', function () {
            var tr = $(this).closest('tr');
            var row = tblSearchCombos.row(tr).data();
            var qty = parseInt(tr.find('input[name="combo_qty"]').val()) || 1;
            if (quotation.addCombo(row, qty)) {
                tblSearchCombos.row(tr).remove().draw();
            }
        });

    // Barcode

    input_search_product.on('keypress', function (e) {
        if (e.which === 13) {
            e.preventDefault();
            execute_ajax_request({
                'params': {
                    'action': 'search_product_code',
                    'code': input_search_product.val(),
                    'customer_type': quotation.customer.customer_type ?? 'retail',
                },
                'success': function (request) {
                    input_search_product.autocomplete('close');
                    if (!$.isEmptyObject(request)) {
                        request.cant = 1;
                        quotation.addProduct(request);
                        input_search_product.val('').focus();
                    } else {
                        message_error('El producto no fue encontrado');
                    }
                }
            });
        }
    });
});