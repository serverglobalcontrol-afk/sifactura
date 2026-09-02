var importXml = {
    lines: [],
    info: {},
    categories: [],
};

function resetImportXmlModal() {
    importXml.lines = [];
    importXml.info = {};
    importXml.categories = [];
    $('#inputImportXmlFile').val('');
    $('#importXmlError').hide().text('');
    $('#importXmlProviderInfo').empty();
    $('#tblImportXmlLines tbody').empty();
    $('#importXmlStepReview').hide();
    $('#importXmlStepUpload').show();
    $('#btnParseImportXml').show();
    $('#btnConfirmImportXml').hide();
}

function importXmlCategoryOptionsHtml() {
    var html = '<option value="">Seleccione...</option>';
    importXml.categories.forEach(function (category) {
        html += '<option value="' + category.id + '">' + category.name + '</option>';
    });
    return html;
}

function renderImportXmlReview() {
    $('#importXmlStepUpload').hide();
    $('#importXmlError').hide();
    $('#importXmlStepReview').show();
    $('#btnParseImportXml').hide();
    $('#btnConfirmImportXml').show();

    var info = importXml.info || {};
    var infoHtml = 'Factura de: <b>' + (info.razon_social || 'proveedor no identificado en el XML') + '</b>';
    if (info.ruc) {
        infoHtml += ' &mdash; RUC: ' + info.ruc;
    }
    infoHtml += '. Se detectaron <b>' + importXml.lines.length + '</b> producto(s) en el detalle.';

    // Número de factura: se completa solo si el campo está vacío, para no
    // pisar algo que la persona ya haya escrito a mano.
    var inputNumber = $('input[name="number"]');
    if (info.invoice_number && !inputNumber.val()) {
        inputNumber.val(info.invoice_number).trigger('change');
        if (typeof fvPurchase !== 'undefined' && fvPurchase) {
            fvPurchase.revalidateField('number');
        }
    }
    if (info.invoice_number_taken) {
        infoHtml += ' <span class="text-danger">Este número de factura ya está registrado en una compra existente.</span>';
    }

    // Proveedor: se cruza por RUC contra el catálogo. Si no hay coincidencia,
    // se avisa para que lo cree con el botón "+" antes de guardar.
    if (info.provider) {
        select_provider.select2('trigger', 'select', {data: info.provider});
        infoHtml += ' <span class="badge badge-success">Proveedor encontrado en el catálogo</span>';
    } else if (info.ruc) {
        infoHtml += ' <span class="badge badge-warning">No existe un proveedor con este RUC en el catálogo &mdash; créelo con el botón "+" antes de guardar</span>';
    }

    $('#importXmlProviderInfo').html(infoHtml);

    var tbody = $('#tblImportXmlLines tbody');
    tbody.empty();

    importXml.lines.forEach(function (line, index) {
        var tr = $('<tr></tr>').attr('data-index', index);
        tr.append($('<td></td>').text(line.code));
        tr.append($('<td></td>').text(line.description));
        tr.append($('<td></td>').append(
            $('<input type="number" min="1" step="1" class="form-control form-control-sm" name="import_cant">').val(line.cant)
        ));

        if (line.product) {
            tr.append($('<td></td>').append(
                $('<input type="number" min="0" step="0.01" class="form-control form-control-sm" name="import_price">').val(line.price.toFixed(2))
            ));

            var matchCell = $('<td></td>');
            matchCell.append($('<span class="badge badge-success"></span>').text('Coincide: ' + line.product.short_name));
            matchCell.append($('<div class="small text-muted"></div>').text('Costo actual en catálogo: $' + parseFloat(line.product.price).toFixed(2)));

            var priceDiffers = Math.abs(parseFloat(line.product.price) - line.price) > 0.001;
            if (priceDiffers) {
                var checkWrap = $('<div class="form-check mt-1"></div>');
                var checkbox = $('<input type="checkbox" class="form-check-input" name="import_update_price">').attr('id', 'importUpdatePrice' + index);
                var label = $('<label class="form-check-label"></label>').attr('for', 'importUpdatePrice' + index)
                    .text('Actualizar precio de costo del producto a $' + line.price.toFixed(2));
                checkWrap.append(checkbox).append(label);
                matchCell.append(checkWrap);
            }
            tr.append(matchCell);
        } else {
            tr.append($('<td></td>').append(
                $('<input type="number" min="0" step="0.01" class="form-control form-control-sm" name="import_new_price">').val(line.price.toFixed(2))
            ));

            var newCell = $('<td></td>');
            newCell.append($('<span class="badge badge-warning"></span>').text('Producto nuevo: se creará al confirmar'));
            var nameInput = $('<input type="text" class="form-control form-control-sm mt-1" name="import_name" placeholder="Nombre del producto">').val(line.description);
            var categorySelect = $('<select class="form-control form-control-sm mt-1" name="import_category"></select>').html(importXmlCategoryOptionsHtml());
            newCell.append(nameInput).append(categorySelect);
            tr.append(newCell);
        }

        tbody.append(tr);
    });
}

function pushImportedProductToPurchase(item) {
    // La cantidad de una línea importada desde el XML no se deja editar en la
    // tabla de detalle: debe reflejar exactamente lo que dice la factura del
    // proveedor. Si se necesita otra cantidad, se elimina la línea y se
    // agrega el producto manualmente.
    item.xml_locked = true;
    var existing = purchase.detail.products.find(function (product) {
        return product.id === item.id;
    });
    if (existing) {
        existing.cant = parseInt(existing.cant) + parseInt(item.cant);
        existing.price = item.price;
        existing.xml_locked = true;
    } else {
        purchase.detail.products.push(item);
    }
}

function processImportXmlRow(index, rows, onDone) {
    if (index >= rows.length) {
        onDone();
        return;
    }
    var row = $(rows[index]);
    var line = importXml.lines[row.data('index')];
    var cant = parseInt(row.find('input[name="import_cant"]').val());
    if (!cant || cant <= 0) {
        cant = 1;
    }

    var next = function () {
        processImportXmlRow(index + 1, rows, onDone);
    };

    if (line.product) {
        var price = parseFloat(row.find('input[name="import_price"]').val());
        if (isNaN(price) || price < 0) {
            price = line.price;
        }
        var item = {
            id: line.product.id,
            code: line.product.code,
            short_name: line.product.short_name,
            cant: cant,
            price: price,
        };
        var wantsUpdate = row.find('input[name="import_update_price"]').is(':checked');
        if (wantsUpdate) {
            $.ajax({
                url: import_xml_pathname,
                type: 'POST',
                dataType: 'json',
                headers: {'X-CSRFToken': csrftoken},
                data: {
                    action: 'update_product_price',
                    id: line.product.id,
                    price: price,
                },
                success: function (response) {
                    if (response.error) {
                        message_error(response.error);
                    }
                    pushImportedProductToPurchase(item);
                    next();
                },
                error: function () {
                    message_error('No se pudo actualizar el precio de costo del producto ' + item.code + '.');
                    pushImportedProductToPurchase(item);
                    next();
                }
            });
        } else {
            pushImportedProductToPurchase(item);
            next();
        }
    } else {
        var name = row.find('input[name="import_name"]').val();
        var category = row.find('select[name="import_category"]').val();
        var newPrice = parseFloat(row.find('input[name="import_new_price"]').val());
        if (isNaN(newPrice) || newPrice < 0) {
            newPrice = line.price;
        }
        $.ajax({
            url: import_xml_pathname,
            type: 'POST',
            dataType: 'json',
            headers: {'X-CSRFToken': csrftoken},
            data: {
                action: 'create_product_from_xml',
                code: line.code,
                name: name,
                category: category,
                price: newPrice,
            },
            success: function (response) {
                if (response.error) {
                    message_error('Producto ' + line.code + ': ' + response.error);
                    next();
                    return;
                }
                pushImportedProductToPurchase({
                    id: response.id,
                    code: response.code,
                    short_name: response.short_name,
                    cant: cant,
                    price: parseFloat(response.price),
                });
                next();
            },
            error: function () {
                message_error('No se pudo crear el producto del código ' + line.code + '.');
                next();
            }
        });
    }
}

$(function () {
    $('.btnImportXml').on('click', function () {
        resetImportXmlModal();
        $('#myModalImportXml').modal('show');
    });

    $('#myModalImportXml').on('hidden.bs.modal', function () {
        resetImportXmlModal();
    });

    $('#btnParseImportXml').on('click', function () {
        var fileInput = $('#inputImportXmlFile')[0];
        var file = fileInput.files.length ? fileInput.files[0] : null;
        $('#importXmlError').hide().text('');

        if (!file || file.name.toLowerCase().split('.').pop() !== 'xml') {
            $('#importXmlError').text('Debe seleccionar un archivo XML válido.').show();
            return;
        }

        var params = new FormData();
        params.append('action', 'parse_xml');
        params.append('archive', file);

        loading({'text': 'Analizando XML...'});
        $.ajax({
            url: import_xml_pathname,
            type: 'POST',
            data: params,
            dataType: 'json',
            processData: false,
            contentType: false,
            headers: {'X-CSRFToken': csrftoken},
            success: function (response) {
                if (response.error) {
                    $('#importXmlError').text(response.error).show();
                    return;
                }
                importXml.lines = response.lines;
                importXml.info = response.info;
                importXml.categories = response.categories;
                renderImportXmlReview();
            },
            error: function () {
                $('#importXmlError').text('No se pudo analizar el archivo XML. Verifique que el archivo no esté dañado.').show();
            },
            complete: function () {
                $.LoadingOverlay('hide');
            }
        });
    });

    $('#btnConfirmImportXml').on('click', function () {
        var rows = $('#tblImportXmlLines tbody tr');
        if (rows.length === 0) {
            return;
        }
        dialog_action({
            content: '¿Confirma agregar estos ' + rows.length + ' producto(s) al detalle de la compra? ' +
                'Esta acción puede crear productos nuevos y/o actualizar precios de costo del catálogo.',
            success: function () {
                loading({'text': 'Importando productos...'});
                processImportXmlRow(0, rows, function () {
                    $.LoadingOverlay('hide');
                    purchase.listProducts();
                    $('#myModalImportXml').modal('hide');
                    alert_sweetalert({
                        'message': 'Productos importados desde el XML correctamente',
                        'timer': 2000,
                        'callback': function () {
                        }
                    });
                });
            },
            cancel: function () {
            }
        });
    });
});
