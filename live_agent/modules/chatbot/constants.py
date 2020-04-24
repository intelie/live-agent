# -*- coding: utf-8 -*-

ITEM_PREFIX = "\n  "
SELECTED_ASSET_VARIABLE_NAME = "selected-asset"

FEATURES_DESCRIPTION_TEMPLATE = """My features are:
{% for feature_data in features %}
  *{{ feature_data.description }}*
  Try: "{{ bot_name }}, {{ feature_data.usage_example }}"
{% endfor %}
"""
