var fv;

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
                counted_amount: {
                    validators: {
                        notEmpty: {
                            message: 'El efectivo contado es obligatorio'
                        },
                        numeric: {
                            message: 'El valor no es un número',
                            thousandsSeparator: '',
                            decimalSeparator: '.'
                        }
                    }
                },
                next_opening_amount: {
                    validators: {
                        numeric: {
                            message: 'El valor no es un número',
                            thousandsSeparator: '',
                            decimalSeparator: '.'
                        },
                        callback: {
                            message: 'No puede ser mayor al efectivo contado',
                            callback: function (input) {
                                if (!input.value) {
                                    return true;
                                }
                                var counted = parseFloat($('#counted_amount').val()) || 0;
                                return parseFloat(input.value) <= counted;
                            }
                        }
                    }
                },
            },
        }
    )
        .on('core.element.validated', function (e) {
            if (e.valid) {
                const groupEle = FormValidation.utils.closest(e.element, '.form-group');
                if (groupEle) {
                    FormValidation.utils.classSet(groupEle, {'has-success': false});
                }
                FormValidation.utils.classSet(e.element, {'is-valid': false});
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
            var args = {
                'content': '¿Confirma el cierre de caja? Esta acción cerrará tu sesión.',
                'params': new FormData(fv.form),
                'success': function (request) {
                    location.href = request.redirect_url;
                }
            };
            submit_with_formdata(args);
        });
});

$(function () {
    $('input[name="counted_amount"]')
        .TouchSpin({
            min: 0,
            max: 1000000,
            step: 0.01,
            decimals: 2,
            boostat: 5,
            maxboostedstep: 10,
            prefix: '$',
        })
        .on('change touchspin.on.min touchspin.on.max', function () {
            fv.revalidateField('counted_amount');
            fv.revalidateField('next_opening_amount');
        });

    // Sin TouchSpin en este campo: es opcional (vacío = no se deja nada
    // designado), y TouchSpin fuerza un valor numérico al inicializarse
    // incluso si el input arranca vacío.
    $('input[name="next_opening_amount"]').on('keyup change', function () {
        fv.revalidateField('next_opening_amount');
    });

    $('i[data-field="counted_amount"]').hide();
    $('i[data-field="next_opening_amount"]').hide();
});
