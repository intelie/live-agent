# -*- coding: utf-8 -*-


def filter_dict(source_dict, filter_func):
    return dict(
        (key, value)
        for key, value in source_dict.items()
        if filter_func(key, value)
    )
