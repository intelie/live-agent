# -*- coding: utf-8 -*-

ITEM_PREFIX = "\n  "

FEATURES_DESCRIPTION_TEMPLATE = """My features are:
{% for feature_data in features %}
  *{{ feature_data.description }}*
  Try: _"{{ bot_name }}, {{ feature_data.usage_example }}"_
{% endfor %}
"""
