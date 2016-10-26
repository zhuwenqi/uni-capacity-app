/**
 * Created by Rongxin on 6/2/2016.
 */
$(function () {

    var checkAllCheckBox = function () {
        var checked = ($(this).prop('checked'))
        $(this).parent().siblings().children('input:checkbox').prop('checked', checked)
    }

    $('.select-all').on('click', checkAllCheckBox)
})