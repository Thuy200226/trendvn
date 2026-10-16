"""Keep a persistent-profile window available until the owner finishes or explicitly closes it."""

from .browser_errors import navigation_error


class OwnerClosed(ValueError):
    pass


def wait(page, ready, pulse=None):
    """No automatic navigation or deadline while the owner is interacting with the page."""
    while not page.is_closed():
        if pulse:
            pulse()
        if ready():
            return
        try:
            page.wait_for_timeout(2000)
        except Exception as error:
            if not page.is_closed() and not navigation_error(error):
                raise
    raise OwnerClosed("Bạn đã đóng cửa sổ để dừng; chưa thực hiện thao tác xóa.")
