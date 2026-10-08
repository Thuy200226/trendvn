"""Accessible form controls and action forms; attributes and visible text are escaped in one place."""

import re
from .format import escape as E
from .icons import icon


def attributes(values):
    result = []
    for key, value in values.items():
        key = key.rstrip("_").replace("_", "-")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", key) or key.startswith("on"):
            raise ValueError("Thuộc tính giao diện không hợp lệ")
        if value is True:
            result.append(" " + key)
        elif value is not False and value is not None:
            result.append(' %s="%s"' % (key, E(str(value))))
    return "".join(result)


def input_control(name, value="", type="text", **attrs):
    return "<input%s>" % attributes(dict(type=type, name=name, value=value, **attrs))


def hidden(name, value):
    return input_control(name, value, "hidden")


def textarea(name, value="", **attrs):
    return "<textarea%s>%s</textarea>" % (attributes(dict(name=name, **attrs)), E(value))


def select_control(name, current, options, **attrs):
    items = "".join(
        "<option%s>%s</option>" % (attributes({"value": value, "selected": value == current}), E(label)) for value, label in options
    )
    return "<select%s>%s</select>" % (attributes(dict(name=name, **attrs)), items)


def checkbox(name, label, checked=False, value="true", css="check", **attrs):
    return '<label class="%s">%s<span>%s</span></label>' % (
        E(css),
        input_control(name, value, "checkbox", checked=checked, **attrs),
        E(label),
    )


def button(label, css="go", icon_name=None, type="submit", **attrs):
    content = (icon(icon_name) if icon_name else "") + "<span>%s</span>" % E(label)
    return button_content(content, css, type, **attrs)


def button_content(content, css="go", type="submit", **attrs):
    """Compose trusted rendered children; callers escape dynamic text before composing."""
    return "<button%s>%s</button>" % (attributes(dict(class_=css, type=type, **attrs)), content)


def action_form(csrf, action, label, fields=None, css="ghost", icon_name=None, **attrs):
    body = hidden("csrf", csrf) + "".join(hidden(k, v) for k, v in (fields or {}).items())
    return '<form method="post" action="%s" class="inline">%s%s</form>' % (E(action), body, button(label, css, icon_name, **attrs))


def copy_field(value, label="Link đã lưu"):
    return '<div class="copy">%s%s</div>' % (
        input_control("saved_link", value, readonly=True, aria_label="Link đã lưu"),
        button("Chép link", "ghost", type="button", data_copy=True, aria_label="Chép link: " + label),
    )


def tab_link(tab, label, icon_name=None, badge="", compact=False):
    content = ('<span class="ic">%s%s</span><small>%s</small>' % (icon(icon_name), badge, E(label))) if compact else E(label) + badge
    return '<a href="#%s" data-go="%s">%s</a>' % (E(tab), E(tab), content)


def confirmation_dialog():
    """One accessible confirmation surface shared by every consequential dashboard action."""
    return (
        '<dialog id="confirm-action" aria-labelledby="confirm-title" aria-describedby="confirm-message">'
        '<h3 id="confirm-title">Xác nhận thao tác</h3><p id="confirm-message"></p><div class="btns two">'
        + button("Hủy", "ghost", type="button", data_confirm_cancel=True, autofocus=True)
        + button("Xác nhận", "go", type="button", data_confirm_accept=True)
        + "</div></dialog>"
    )
