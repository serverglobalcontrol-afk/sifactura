function esc(value) {
    return $('<div>').text(value == null ? '' : value).html();
}

function call(params, done) {
    $.ajax({
        url: pathname,
        type: 'POST',
        data: params,
        headers: {'X-CSRFToken': csrftoken},
        dataType: 'json',
        beforeSend: function () {
            loading({'text': '...'});
        },
        success: function (request) {
            if (request.hasOwnProperty('error')) {
                message_error(request.error);
                return false;
            }
            done(request);
        },
        error: function (jqXHR, textStatus, errorThrown) {
            message_error(errorThrown + ' ' + textStatus);
        },
        complete: function () {
            $.LoadingOverlay('hide');
        }
    });
}

function addRow(row) {
    row = row || {lower: '', upper: '', base_tax: '0', rate: '0'};
    var html = '<tr>' +
        '<td><input type="text" class="form-control form-control-sm b-lower" value="' + esc(row.lower) + '"></td>' +
        '<td><input type="text" class="form-control form-control-sm b-upper" value="' + esc(row.upper) + '" placeholder="en adelante"></td>' +
        '<td><input type="text" class="form-control form-control-sm b-base" value="' + esc(row.base_tax) + '"></td>' +
        '<td><input type="text" class="form-control form-control-sm b-rate" value="' + esc(row.rate) + '"></td>' +
        '<td class="text-center"><a class="btn btn-danger btn-xs btn-flat btn-remove"><i class="fas fa-trash"></i></a></td></tr>';
    $('#tblBrackets tbody').append(html);
}

function fillForm(item) {
    $('#basicBasket').val(item.basic_basket || '');
    $('#employerType').val(item.employer_type || 'PRIVADO_MIXTO');
    $('#socialSecurity').val(item.social_security || 'IESS');
    $('#galapagosIndex').val(item.galapagos_index || '1.0000');
    $('#source').val(item.source || '');
    $('#tblBrackets tbody').empty();
    (item.brackets || []).forEach(addRow);
}

function collectBrackets() {
    var rows = [];
    $('#tblBrackets tbody tr').each(function () {
        rows.push({
            lower: $(this).find('.b-lower').val(),
            upper: $(this).find('.b-upper').val(),
            base_tax: $(this).find('.b-base').val(),
            rate: $(this).find('.b-rate').val()
        });
    });
    return rows;
}

$(function () {
    $('#btnLoadYear').on('click', function () {
        call({action: 'get', year: $('#rdepYear').val()}, function (request) {
            if (request.exists === false) {
                fillForm({});
                $('#rdepStatus').html('<div class="alert alert-warning py-2 mb-2">No hay parámetros para ' + request.year + ' todavía. ' +
                    (SUGGESTED_YEARS.indexOf(request.year) !== -1 ? 'Usa <b>Cargar valores del SRI</b> y revísalos.' : 'Cárgalos a mano.') + '</div>');
                return;
            }
            fillForm(request);
            $('#rdepStatus').html('<div class="alert alert-success py-2 mb-2">Parámetros de ' + request.year + ' guardados.</div>');
        });
    });

    $('#btnSuggest').on('click', function () {
        call({action: 'suggest', year: $('#rdepYear').val()}, function (request) {
            fillForm(request);
            $('#rdepStatus').html('<div class="alert alert-info py-2 mb-2">Valores cargados desde lo publicado por el SRI. <b>Todavía no están guardados</b>: revísalos y pulsa Guardar.</div>');
        });
    });

    $('#btnAddRow').on('click', function () {
        addRow();
    });

    $('#tblBrackets').on('click', '.btn-remove', function () {
        $(this).closest('tr').remove();
    });

    $('#btnSave').on('click', function () {
        call({
            action: 'save',
            year: $('#rdepYear').val(),
            basic_basket: $('#basicBasket').val(),
            employer_type: $('#employerType').val(),
            social_security: $('#socialSecurity').val(),
            galapagos_index: $('#galapagosIndex').val(),
            source: $('#source').val(),
            brackets: JSON.stringify(collectBrackets())
        }, function () {
            alert_sweetalert({
                'title': 'Guardado',
                'type': 'success',
                'message': 'Los parámetros del RDEP se guardaron correctamente.',
                'timer': null,
                'callback': function () {
                    $('#btnLoadYear').click();
                }
            });
        });
    });

    $('#btnLoadYear').click();
});
