$(function () {
    $('#frmForm').on('submit', function (e) {
        e.preventDefault();
        submit_with_formdata({'params': new FormData(this), 'form': this});
    });
});
