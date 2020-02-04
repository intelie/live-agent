from contextlib import contextmanager

@contextmanager
def manage_action(action):
    try:
        yield action
    finally:
        action.finish()
