"""Recognize transient Playwright failures without requiring Chrome dependencies in worker-side unit tests."""


def navigation_error(error):
    return type(error).__module__.startswith("playwright.")
