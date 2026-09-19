var retention = {
    sale: null,
    open: function (row) {
        retention.sale = row;
        $('#retentionSaleNumber').text(row.voucher_number_full || row.number || '');
        $('#retentionError').hide().text('');
        $('#inputRetentionXmlFile').val('');
        $('#retentionDocumentNumber').val('');
        $('#retentionIssueDate').val('');
        $('#retentionAccessCode').val('');
        $('#retentionAgentRuc').val(row.client && row.client.dni ? row.client.dni : '');
        $('#retentionAgentName').val(row.client && row.client.user ? row.client.user.names : '');
        $('#retentionIvaRetained').val('0.00');
        $('#retentionIncomeTaxRetained').val('0.00');
        $('#retentionTotalRetained').val('0.00');
        $('#retentionObservations').val('');
        $('#retentionTabXml a').tab('show');
        retention.list(row.id);
        $('#myModalRetention').modal('show');
    },
    list: function (saleId) {
        $.ajax({
            url: retention_pathname,
            type: 'POST',
            dataType: 'json',
            headers: {'X-CSRFToken': csrftoken},
            data: {action: 'search', sale: saleId},
            success: function (rows) {
                retention.renderList(rows || []);
            }
        });
    },
    renderList: function (rows) {
        var tbody = $('#tblRetentions tbody');
        tbody.empty();
        if (!rows.length) {
            tbody.append('<tr><td colspan="8" class="text-center text-muted">Sin retenciones registradas para esta factura</td></tr>');
            return;
        }
        rows.forEach(function (row) {
            var tr = $('<tr></tr>');
            tr.append($('<td></td>').text(row.document_number));
            tr.append($('<td></td>').text(row.issue_date));
            tr.append($('<td></td>').text(row.agent_name || row.agent_ruc || '-'));
            tr.append($('<td class="text-right"></td>').text('$' + row.iva_retained.toFixed(2)));
            tr.append($('<td class="text-right"></td>').text('$' + row.income_tax_retained.toFixed(2)));
            tr.append($('<td class="text-right"></td>').text('$' + row.total_retained.toFixed(2)));
            tr.append($('<td></td>').text(row.created_by ? row.created_by.names : '-'));
            var actions = $('<td class="text-center"></td>');
            var deleteBtn = $('<a class="btn btn-danger btn-xs btn-flat" data-toggle="tooltip" title="Eliminar"><i class="fas fa-trash-alt"></i></a>');
            deleteBtn.on('click', function () {
                retention.remove(row.id);
            });
            actions.append(deleteBtn);
            tr.append(actions);
            tbody.append(tr);
        });
    },
    remove: function (id) {
        dialog_action({
            content: '¿Esta seguro de eliminar esta retención? El saldo pendiente de la factura volverá a aumentar por ese valor.',
            success: function () {
                loading({'text': '...'});
                $.ajax({
                    url: pathname + 'retention/delete/' + id + '/',
                    type: 'POST',
                    dataType: 'json',
                    headers: {'X-CSRFToken': csrftoken},
                    success: function (response) {
                        if (response && response.error) {
                            message_error(response.error);
                            return;
                        }
                        retention.list(retention.sale.id);
                        tblSale.ajax.reload();
                    },
                    complete: function () {
                        $.LoadingOverlay('hide');
                    }
                });
            },
            cancel: function () {
            }
        });
    },
    recalculateTotal: function () {
        var iva = parseFloat($('#retentionIvaRetained').val()) || 0;
        var renta = parseFloat($('#retentionIncomeTaxRetained').val()) || 0;
        $('#retentionTotalRetained').val((iva + renta).toFixed(2));
    }
};

$(function () {
    $('#retentionIvaRetained, #retentionIncomeTaxRetained').on('keyup change', retention.recalculateTotal);

    $('#myModalRetention').on('hidden.bs.modal', function () {
        retention.sale = null;
    });

    $('#btnParseRetentionXml').on('click', function () {
        var fileInput = $('#inputRetentionXmlFile')[0];
        var file = fileInput.files.length ? fileInput.files[0] : null;
        $('#retentionError').hide().text('');

        if (!file || file.name.toLowerCase().split('.').pop() !== 'xml') {
            $('#retentionError').text('Debe seleccionar un archivo XML válido.').show();
            return;
        }

        var params = new FormData();
        params.append('action', 'parse_xml');
        params.append('archive', file);

        loading({'text': 'Analizando XML...'});
        $.ajax({
            url: retention_pathname,
            type: 'POST',
            data: params,
            dataType: 'json',
            processData: false,
            contentType: false,
            headers: {'X-CSRFToken': csrftoken},
            success: function (response) {
                if (response.error) {
                    $('#retentionError').text(response.error).show();
                    return;
                }
                var info = response.info || {};
                $('#retentionDocumentNumber').val(info.document_number || '');
                $('#retentionIssueDate').val(response.issue_date || '');
                $('#retentionAccessCode').val(info.clave_acceso || '');
                $('#retentionAgentRuc').val(info.ruc || '');
                $('#retentionAgentName').val(info.razon_social || '');
                $('#retentionIvaRetained').val(response.iva_retained.toFixed(2));
                $('#retentionIncomeTaxRetained').val(response.income_tax_retained.toFixed(2));
                retention.recalculateTotal();
                alert_sweetalert({
                    'message': 'XML analizado correctamente. Revise los datos antes de registrar.',
                    'timer': 2000,
                    'callback': function () {
                    }
                });
            },
            error: function () {
                $('#retentionError').text('No se pudo analizar el archivo XML. Verifique que el archivo no esté dañado.').show();
            },
            complete: function () {
                $.LoadingOverlay('hide');
            }
        });
    });

    $('#btnSaveRetention').on('click', function () {
        if (!retention.sale) {
            return;
        }
        $('#retentionError').hide().text('');

        var params = new FormData();
        params.append('action', 'add');
        params.append('sale', retention.sale.id);
        params.append('document_number', $('#retentionDocumentNumber').val());
        params.append('issue_date', $('#retentionIssueDate').val());
        params.append('access_code', $('#retentionAccessCode').val());
        params.append('agent_ruc', $('#retentionAgentRuc').val());
        params.append('agent_name', $('#retentionAgentName').val());
        params.append('iva_retained', $('#retentionIvaRetained').val());
        params.append('income_tax_retained', $('#retentionIncomeTaxRetained').val());
        params.append('observations', $('#retentionObservations').val());
        var fileInput = $('#inputRetentionXmlFile')[0];
        if (fileInput.files.length) {
            params.append('archive', fileInput.files[0]);
        }

        dialog_action({
            content: '¿Esta seguro de registrar esta retención? El saldo pendiente de la factura bajará por el total retenido.',
            success: function () {
                loading({'text': 'Registrando retención...'});
                $.ajax({
                    url: retention_pathname,
                    type: 'POST',
                    data: params,
                    dataType: 'json',
                    processData: false,
                    contentType: false,
                    headers: {'X-CSRFToken': csrftoken},
                    success: function (response) {
                        if (response.error) {
                            $('#retentionError').text(response.error).show();
                            return;
                        }
                        alert_sweetalert({
                            'message': 'Retención registrada correctamente',
                            'timer': 2000,
                            'callback': function () {
                                retention.list(retention.sale.id);
                                tblSale.ajax.reload();
                            }
                        });
                        $('#retentionDocumentNumber').val('');
                        $('#retentionIssueDate').val('');
                        $('#retentionAccessCode').val('');
                        $('#retentionIvaRetained').val('0.00');
                        $('#retentionIncomeTaxRetained').val('0.00');
                        $('#retentionTotalRetained').val('0.00');
                        $('#retentionObservations').val('');
                        $('#inputRetentionXmlFile').val('');
                    },
                    error: function () {
                        $('#retentionError').text('No se pudo registrar la retención.').show();
                    },
                    complete: function () {
                        $.LoadingOverlay('hide');
                    }
                });
            },
            cancel: function () {
            }
        });
    });
});
