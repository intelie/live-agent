import time


def retry_on_error(fn, exception_cls, delay=0):
    try:
        return fn()
    except exception_cls:
        time.sleep(delay)
        return fn()
