function add_line() {
    var options = $('#accountTemplate').html();
    var row = '<tr>' +
        '<td><select class="form-control form-control-sm line-account">' + options + '</select></td>' +
        '<td><input type="text" class="form-control form-control-sm line-description" maxlength="300"></td>' +
        '<td><input type="number" min="0" step="0.01" class="form-control form-control-sm text-right line-debit"></td>' +
        '<td><input type="number" min="0" step="0.01" class="form-control form-control-sm text-right line-credit"></td>' +
        '<td class="text-center"><a rel="remove" class="btn btn-danger btn-xs btn-flat"><i class="fas fa-times"></i></a></td>' +
        '</tr>';
    $('#tblLines tbody').append(row);
}

function recalculate() {
    var debit = 0;
    var credit = 0;
    $('#tblLines tbody tr').each(function () {
        debit += parseFloat($(this).find('.line-debit').val()) || 0;
        credit += parseFloat($(this).find('.line-credit').val()) || 0;
    });
    $('#totalDebit').text('$' + debit.toFixed(2));
    $('#totalCredit').text('$' + credit.toFixed(2));
    var diff = Math.round((debit - credit) * 100) / 100;
    $('#difference').text('$' + diff.toFixed(2)).toggleClass('text-danger', diff !== 0).toggleClass('text-success', diff === 0);
}

$(function () {
    add_line();
    add_line();

    $('#btnAddLine').on('click', add_line);

    $('#tblLines tbody')
        .on('click', 'a[rel="remove"]', function () {
            $(this).closest('tr').remove();
            recalculate();
        })
        .on('input', '.line-debit, .line-credit', function () {
            // Una línea va al Debe o al Haber, no a ambos.
            var row = $(this).closest('tr');
            if ($(this).hasClass('line-debit') && $(this).val()) {
                row.find('.line-credit').val('');
            } else if ($(this).hasClass('line-credit') && $(this).val()) {
                row.find('.line-debit').val('');
            }
            recalculate();
        });

    $('#frmForm').on('submit', function (e) {
        e.preventDefault();
        var lines = [];
        $('#tblLines tbody tr').each(function () {
            var account = $(this).find('.line-account').val();
            var debit = $(this).find('.line-debit').val();
            var credit = $(this).find('.line-credit').val();
            if (account && (parseFloat(debit) > 0 || parseFloat(credit) > 0)) {
                lines.push({
                    'account': account,
                    'debit': debit || 0,
                    'credit': credit || 0,
                    'description': $(this).find('.line-description').val()
                });
            }
        });
        if (lines.length < 2) {
            message_error('El asiento necesita al menos dos líneas con cuenta y valor.');
            return false;
        }
        var params = new FormData();
        params.append('action', 'add');
        params.append('csrfmiddlewaretoken', $('input[name="csrfmiddlewaretoken"]').val());
        params.append('date', $('#entryDate').val());
        params.append('description', $('#entryDescription').val());
        params.append('lines', JSON.stringify(lines));
        submit_with_formdata({'params': params, 'form': this});
    });
});
