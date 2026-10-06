var tblBank, tblBook;
var selectedBank = null, selectedBook = null;

function money(value) {
    var number = parseFloat(value) || 0;
    return (number < 0 ? '-$' : '$') + Math.abs(number).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

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

function card(title, value, extra, cls) {
    return '<div class="col-lg-3 col-md-6"><div class="small-box bg-light border"><div class="inner" style="padding:8px 12px;">' +
        '<p class="mb-0 text-muted">' + title + '</p><h4 class="mb-0 ' + (cls || '') + '">' + value + '</h4>' +
        (extra ? '<small class="text-muted">' + extra + '</small>' : '') + '</div></div></div>';
}

function loadSummary() {
    call({action: 'summary'}, function (request) {
        var s = request.summary;
        var diffClass = s.balanced ? 'text-success' : 'text-danger';
        $('#summaryCards').html(
            card('Saldo según el banco', money(s.bank_closing), 'al ' + request.statement.date_to) +
            card('Saldo según el libro', money(s.book_balance), 'cuenta contable de este banco') +
            card('Libro sin conciliar', money(s.book_pending_total), s.book_pending_count + ' línea(s): lo que el banco aún no refleja') +
            card('Banco sin conciliar', money(s.bank_pending_total), s.bank_pending_count + ' movimiento(s): lo que falta registrar') +
            card('Banco ajustado', money(s.adjusted_bank), 'saldo banco + libro sin conciliar') +
            card('Libro ajustado', money(s.adjusted_book), 'saldo libro + banco sin conciliar') +
            card('DIFERENCIA', money(s.difference), s.balanced ? 'Conciliado: puedes cerrar' : 'Debe ser 0.00 para cerrar', diffClass)
        );
        var note = '';
        if (s.opening_marked) {
            note += s.opening_marked + ' asiento(s) anteriores al período están dados por conciliados (ya estaban en el saldo inicial del banco). ';
        }
        if (s.opening_balance !== null && Math.abs(s.opening_balance - s.book_before_start) >= 0.005) {
            note += 'El saldo inicial del banco (' + money(s.opening_balance) + ') no coincide con el libro antes del período (' + money(s.book_before_start) + '): hay partidas anteriores sin conciliar.';
        }
        $('#openingNote').html(note ? '<div class="alert alert-info py-2 mb-3">' + esc(note) + '</div>' : '');
        var open = request.statement.status.id === 'open';
        $('#btnReconcile, #btnAutoMatch, #btnMatchSelected, #btnSetClosing, #btnMarkOpening, #btnPostAll').toggle(open);
        $('#btnPostOpening').toggle(open && s.opening_balance !== null && Math.abs(s.opening_balance - s.book_before_start) >= 0.005);
        $('#btnReopen').toggle(!open);
    });
}

function reloadAll() {
    selectedBank = null;
    selectedBook = null;
    tblBank.ajax.reload();
    tblBook.ajax.reload();
    loadSummary();
}

$(function () {
    tblBank = $('#tblBank').DataTable({
        autoWidth: false,
        paging: false,
        ordering: false,
        ajax: {url: pathname, type: 'POST', headers: {'X-CSRFToken': csrftoken}, data: {action: 'bank_lines'}, dataSrc: ''},
        columns: [{data: 'date'}, {data: 'description'}, {data: 'reference'}, {data: 'amount'}, {data: 'matched'}, {data: 'id'}],
        columnDefs: [
            {targets: [1], render: function (data) { return esc(data); }},
            {targets: [3], class: 'text-right', render: function (data) {
                return '<span class="' + (data < 0 ? 'text-danger' : 'text-success') + '">' + money(data) + '</span>';
            }},
            {targets: [4], render: function (data, type, row) {
                return row.matched ? '<span class="badge badge-success">' + esc(row.entry) + '</span>' : '<span class="badge badge-warning">Pendiente</span>';
            }},
            {targets: [5], class: 'text-center', orderable: false, render: function (data, type, row) {
                if (!STATEMENT_OPEN) {
                    return '';
                }
                if (row.matched) {
                    return '<a rel="unmatch" class="btn btn-secondary btn-xs btn-flat" title="Desconciliar"><i class="fas fa-unlink"></i></a>';
                }
                return '<a rel="post" class="btn btn-info btn-xs btn-flat" title="Registrar en el libro"><i class="fas fa-plus"></i></a> ' +
                    '<a rel="flip" class="btn btn-warning btn-xs btn-flat" title="Invertir signo (depósito/retiro)"><i class="fas fa-exchange-alt"></i></a> ' +
                    '<a rel="remove" class="btn btn-danger btn-xs btn-flat" title="Quitar este movimiento"><i class="fas fa-trash"></i></a>';
            }},
        ],
        createdRow: function (row, data) {
            if (!data.matched) {
                $(row).css('cursor', 'pointer');
            }
        },
        language: {emptyTable: 'Sin movimientos'}
    });

    tblBook = $('#tblBook').DataTable({
        autoWidth: false,
        paging: false,
        ordering: false,
        ajax: {url: pathname, type: 'POST', headers: {'X-CSRFToken': csrftoken}, data: {action: 'book_lines'}, dataSrc: ''},
        columns: [{data: 'date'}, {data: 'entry'}, {data: 'description'}, {data: 'amount'}],
        columnDefs: [
            {targets: [2], render: function (data) { return esc(data); }},
            {targets: [3], class: 'text-right', render: function (data) {
                return '<span class="' + (data < 0 ? 'text-danger' : 'text-success') + '">' + money(data) + '</span>';
            }},
        ],
        createdRow: function (row) {
            $(row).css('cursor', 'pointer');
        },
        language: {emptyTable: 'Todo el libro está conciliado'}
    });

    $('#tblBank tbody').on('click', 'tr', function (e) {
        if ($(e.target).closest('a').length) {
            return;
        }
        var row = tblBank.row(this).data();
        if (!row || row.matched || !STATEMENT_OPEN) {
            return;
        }
        $('#tblBank tbody tr').removeClass('table-primary');
        $(this).addClass('table-primary');
        selectedBank = row;
    });

    $('#tblBook tbody').on('click', 'tr', function () {
        var row = tblBook.row(this).data();
        if (!row || !STATEMENT_OPEN) {
            return;
        }
        $('#tblBook tbody tr').removeClass('table-primary');
        $(this).addClass('table-primary');
        selectedBook = row;
    });

    $('#tblBank tbody').on('click', 'a[rel="unmatch"]', function () {
        var row = tblBank.row($(this).closest('tr')).data();
        call({action: 'unmatch', line: row.id}, reloadAll);
    });

    $('#tblBank tbody').on('click', 'a[rel="flip"]', function () {
        var row = tblBank.row($(this).closest('tr')).data();
        call({action: 'flip_sign', line: row.id}, reloadAll);
    });

    $('#tblBank tbody').on('click', 'a[rel="remove"]', function () {
        var row = tblBank.row($(this).closest('tr')).data();
        dialog_action({
            'title': 'Quitar movimiento',
            'content': 'Se quita este movimiento del estado de cuenta cargado (no se toca el libro). ¿Desea continuar?',
            'success': function () {
                call({action: 'delete_line', line: row.id}, reloadAll);
            },
            'cancel': function () {
            }
        });
    });

    $('#tblBank tbody').on('click', 'a[rel="post"]', function () {
        var row = tblBank.row($(this).closest('tr')).data();
        $('#postLine').val(row.id);
        $('#postText').text('Movimiento del banco: ' + row.description + ' por ' + money(row.amount) + '. Se creará el asiento en el libro con la cuenta contraria que elijas.');
        var preferred = row.amount < 0 ? DEFAULT_EXPENSE : DEFAULT_INCOME;
        if (preferred) {
            $('#postAccount').val(preferred);
        }
        $('#myModalPost').modal('show');
    });

    $('#btnPost').on('click', function () {
        call({action: 'post', line: $('#postLine').val(), account: $('#postAccount').val()}, function () {
            $('#myModalPost').modal('hide');
            reloadAll();
        });
    });

    $('#btnAutoMatch').on('click', function () {
        call({action: 'auto_match'}, function (request) {
            alert_sweetalert({
                'title': 'Conciliación automática',
                'type': request.matched ? 'success' : 'info',
                'message': request.matched + ' movimiento(s) conciliados por valor y fecha.',
                'timer': null,
                'callback': reloadAll
            });
        });
    });

    $('#btnMatchSelected').on('click', function () {
        if (!selectedBank || !selectedBook) {
            message_error('Elige un movimiento del banco (sin conciliar) y una línea del libro, y vuelve a pulsar.');
            return false;
        }
        call({action: 'match', line: selectedBank.id, entry_line: selectedBook.id}, reloadAll);
    });

    $('#btnMarkOpening').on('click', function () {
        dialog_action({
            'title': 'Marcar anteriores como conciliados',
            'content': 'Se dan por conciliados los asientos de esta cuenta anteriores al período del estado de cuenta (el banco ya los tenía). Úsalo solo en la primera conciliación. ¿Desea continuar?',
            'success': function () {
                call({action: 'mark_opening'}, reloadAll);
            },
            'cancel': function () {
            }
        });
    });

    $('#btnPostOpening').on('click', function () {
        if (DEFAULT_CAPITAL) {
            $('#openingAccount').val(DEFAULT_CAPITAL);
        }
        $('#myModalOpening').modal('show');
    });

    $('#btnOpeningSave').on('click', function () {
        call({action: 'post_opening', account: $('#openingAccount').val()}, function () {
            $('#myModalOpening').modal('hide');
            reloadAll();
        });
    });

    $('#btnPostAll').on('click', function () {
        if (DEFAULT_INCOME) {
            $('#allIncome').val(DEFAULT_INCOME);
        }
        if (DEFAULT_GENERAL) {
            $('#allExpense').val(DEFAULT_GENERAL);
        }
        if (DEFAULT_EXPENSE) {
            $('#allFee').val(DEFAULT_EXPENSE);
        }
        $('#myModalPostAll').modal('show');
    });

    $('#btnPostAllSave').on('click', function () {
        call({action: 'post_all', income_account: $('#allIncome').val(), expense_account: $('#allExpense').val(), fee_account: $('#allFee').val()}, function (request) {
            $('#myModalPostAll').modal('hide');
            alert_sweetalert({
                'title': 'Movimientos registrados',
                'type': 'success',
                'message': request.posted + ' movimiento(s) registrados en el libro y conciliados.',
                'timer': null,
                'callback': reloadAll
            });
        });
    });

    $('#btnSetClosing').on('click', function () {
        var value = prompt('Saldo final según el banco (por ejemplo 1347.50):');
        if (value === null || value === '') {
            return;
        }
        call({action: 'set_closing', closing_balance: value}, reloadAll);
    });

    $('#btnReconcile').on('click', function () {
        dialog_action({
            'title': 'Cerrar conciliación',
            'content': 'Se marca como conciliada. Después ya no se cambian emparejamientos salvo que la reabras. ¿Desea continuar?',
            'success': function () {
                call({action: 'reconcile'}, function () {
                    location.reload();
                });
            },
            'cancel': function () {
            }
        });
    });

    $('#btnReopen').on('click', function () {
        call({action: 'reopen'}, function () {
            location.reload();
        });
    });

    loadSummary();
});
