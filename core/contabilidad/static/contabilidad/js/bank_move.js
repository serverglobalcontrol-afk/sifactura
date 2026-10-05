// Cada tipo de movimiento bancario pide datos distintos: el formulario cambia
// las etiquetas, muestra la cuenta destino solo en transferencias y exige el
// número de comprobante solo ahí. El servidor valida igual (BankMoveForm.clean),
// esto es solo para que el usuario vea únicamente lo que necesita.
var MOVE_TYPES = {
    deposit: {
        account: 'Cuenta en la que se deposita',
        reference: 'N° de papeleta de depósito (opcional)',
        help: 'El efectivo sale de la Caja general y entra a la cuenta bancaria elegida.',
        transfer: false,
    },
    withdrawal: {
        account: 'Cuenta de la que se retira',
        reference: 'N° de comprobante de retiro (opcional)',
        help: 'El dinero sale de la cuenta bancaria elegida y entra a la Caja general.',
        transfer: false,
    },
    transfer: {
        account: 'Cuenta de origen',
        reference: 'N° de comprobante de la transferencia',
        help: 'El dinero sale de la cuenta de origen y entra a la cuenta de destino. El comprobante es obligatorio.',
        transfer: true,
    },
    fee: {
        account: 'Cuenta bancaria que paga la comisión',
        reference: 'N° de nota de débito (opcional)',
        help: 'La comisión se descuenta de la cuenta bancaria y se registra como gasto bancario.',
        transfer: false,
    },
};

function apply_move_type() {
    var cfg = MOVE_TYPES[$('#id_kind').val()];
    $('#lblBankAccount').text(cfg.account + ':');
    $('#lblReference').text(cfg.reference + ':');
    $('#moveHelp').text(cfg.help);
    // Los campos ocultos se deshabilitan para que ni siquiera se envíen.
    $('#groupOtherAccount').toggle(cfg.transfer);
    $('#id_other_bank_account').prop('disabled', !cfg.transfer);
    if (!cfg.transfer) {
        $('#id_other_bank_account').val('');
    }
    $('#id_reference').prop('required', cfg.transfer);
}

$(function () {
    $('#id_kind').on('change', apply_move_type);
    apply_move_type();

    $('#frmForm').on('submit', function (e) {
        e.preventDefault();
        if (!$('#id_bank_account').val()) {
            message_error('Elige la cuenta bancaria.');
            return false;
        }
        if (MOVE_TYPES[$('#id_kind').val()].transfer) {
            if (!$('#id_other_bank_account').val()) {
                message_error('Elige la cuenta de destino de la transferencia.');
                return false;
            }
            if ($('#id_other_bank_account').val() === $('#id_bank_account').val()) {
                message_error('La cuenta de destino debe ser distinta a la de origen.');
                return false;
            }
            if (!$.trim($('#id_reference').val())) {
                message_error('El número de comprobante de la transferencia es obligatorio.');
                return false;
            }
        }
        submit_with_formdata({'params': new FormData(this), 'form': this});
    });
});
