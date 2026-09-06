document.addEventListener('DOMContentLoaded', function (e) {
    var fv = FormValidation.formValidation(document.getElementById('frmForm'), {
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
                system_name: {
                    validators: {
                        notEmpty: {},
                        stringLength: {
                            min: 2,
                        },
                    }
                },
                ruc: {
                    validators: {
                        notEmpty: {},
                        stringLength: {
                            min: 10,
                            max: 13,
                        },
                    }
                },
                website: {
                    validators: {
                        notEmpty: {},
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
