document.addEventListener('DOMContentLoaded', function (e) {
    const fv = FormValidation.formValidation(document.getElementById('frmForm'), {
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
                email_host: {
                    validators: {
                        notEmpty: {},
                    }
                },
                email_port: {
                    validators: {
                        digits: {},
                        notEmpty: {},
                    }
                },
                email_host_user: {
                    validators: {
                        notEmpty: {},
                    }
                },
                email_host_password: {
                    // Esta página es siempre de edición: dejarlo en blanco
                    // significa "no cambiar la clave actual" (nunca se
                    // re-muestra el valor guardado), así que no puede ser
                    // obligatorio.
                    validators: {
                        notEmpty: {enabled: false},
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
            var params = new FormData(fv.form);
            var args = {
                'params': params,
                'form': fv.form
            };
            submit_with_formdata(args);
        });
});

$(function () {
    $('input[name="email_port"]').on('keypress', function (e) {
        return validate_text_box({'event': e, 'type': 'numbers'});
    });

    $('.btnShowPassword').on('click', function () {
        var i = $(this).find('i');
        var input = $(this).parent().parent().find('input');
        if (i.hasClass('fa fa-eye-slash')) {
            i.removeClass();
            i.addClass('fa fa-eye');
            input.attr('type', 'password');
        } else {
            i.removeClass();
            i.addClass('fa fa-eye-slash');
            input.attr('type', 'text');
        }
    });

    $('i[data-field="email_host_password"]').hide();

    $('.btnDisconnectGoogleDrive').on('click', function () {
        var scope = $(this).data('scope');
        var formData = new FormData();
        formData.append('action', 'disconnect');
        var args = {
            'params': formData,
            'pathname': `/tenant/google-drive/disconnect/${scope}/`,
            'content': '¿Deseas desconectar esta cuenta de Google Drive? Los próximos respaldos dejarán de subirse a la nube.',
            'success': function () {
                location.reload();
            }
        };
        submit_with_formdata(args);
    });

    var params = new URLSearchParams(window.location.search);
    if (params.has('google_drive_connected')) {
        alert_sweetalert({
            'message': 'Google Drive conectado correctamente',
            'timer': 2500,
            'callback': function () {
                window.history.replaceState({}, document.title, window.location.pathname);
            }
        });
    } else if (params.has('google_drive_error')) {
        message_error('No se pudo conectar con Google Drive: ' + params.get('google_drive_error'));
        window.history.replaceState({}, document.title, window.location.pathname);
    }
});