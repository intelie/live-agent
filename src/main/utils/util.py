def attempt(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except:
        return None
