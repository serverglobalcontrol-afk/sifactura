var fv;
var input_hiring_date;

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
                names: {
                    validators: {
                        notEmpty: {},
                        stringLength: {
                            min: 2,
                        },
                    }
                },
                dni: {
                    validators: {
                        notEmpty: {},
                        digits: {},
                        remote: {
                            url: pathname,
                            data: function () {
                                return {
                                    parameter: fv.form.querySelector('[name="dni"]').value,
                                    pattern: 'dni',
                                    action: 'validate_data'
                                };
                            },
                            message: 'El número de documento ya se encuentra registrado',
                            method: 'POST',
                            headers: {
                                'X-CSRFToken': csrftoken
                            }
                        }
                    }
                },
                code: {
                    validators: {
                        notEmpty: {},
                        stringLength: {
                            min: 1
                        },
                        remote: {
                            url: pathname,
                            data: function () {
                                return {
                                    parameter: fv.form.querySelector('[name="code"]').value,
                                    pattern: 'code',
                                    action: 'validate_data'
                                };
                            },
                            message: 'El código del empleado ya se encuentra registrado',
                            method: 'POST',
                            headers: {
                                'X-CSRFToken': csrftoken
                            }
                        }
                    }
                },
                hiring_date: {
                    validators: {
                        notEmpty: {
                            message: 'La fecha es obligatoria'
                        },
                        date: {
                            format: 'YYYY-MM-DD',
                            message: 'La fecha no es válida'
                        }
                    },
                },
                image: {
                    validators: {
                        file: {
                            extension: 'jpeg,jpg,png',
                            type: 'image/jpeg,image/png',
                            maxFiles: 1,
                            message: 'Introduce una imagen válida'
                        }
                    }
                },
                position: {
                    validators: {
                        notEmpty: {
                            message: 'Seleccione un cargo'
                        },
                    }
                },
                area: {
                    validators: {
                        notEmpty: {
                            message: 'Seleccione un área'
                        },
                    }
                },
                remuneration: {
                    validators: {
                        notEmpty: {},
                        numeric: {
                            message: 'El valor no es un número',
                            thousandsSeparator: '',
                            decimalSeparator: '.'
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
            var args = {
                'params': new FormData(fv.form),
                'form': fv.form
            };
            submit_with_formdata(args);
        });
});

$(function () {

    input_hiring_date = $('input[name="hiring_date"]');

    input_hiring_date.datetimepicker({
        useCurrent: false,
        format: 'YYYY-MM-DD',
        locale: 'es',
        keepOpen: false,
    });

    input_hiring_date.on('change.datetimepicker', function (e) {
        fv.revalidateField('hiring_date');
    });

    $('input[name="names"]').on('keypress', function (e) {
        return validate_text_box({'event': e, 'type': 'letters'});
    });

    $('input[name="dni"]').on('keypress', function (e) {
        return validate_text_box({'event': e, 'type': 'numbers'});
    });

    $('input[name="code"]')
        .on('keyup', function (e) {
            var text = $(this).val();
            $(this).val(text.toUpperCase());
        })
        .on('keypress', function (e) {
            return validate_text_box({'event': e, 'type': 'numbers_letters'});
        });

    $('input[name="mobile"]').on('keypress', function (e) {
        return validate_text_box({'event': e, 'type': 'numbers'});
    });

    $('.select2').select2({
        theme: 'bootstrap4',
        language: "es"
    });

    $('select[name="position"]').on('change', function () {
        fv.revalidateField('position');
    });

    $('select[name="area"]').on('change', function () {
        fv.revalidateField('area');
    });

    $('input[name="remuneration"]').on('keypress', function (e) {
        return validate_text_box({'event': e, 'type': 'decimals'});
    });
});