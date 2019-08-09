# -*- coding: utf-8 -*-

__all__ = [
    'get_positive_examples',
    'get_negative_examples',
]


def get_positive_examples(key):
    return FEATURES[key]['examples']


def get_negative_examples(key):
    examples = NEGATIVE_EXAMPLES
    for feature_key, feature_data in FEATURES.items():
        if feature_key != key:
            examples.extend(feature_data.get('examples', []))

    return examples

FEATURES = {
    'asset-list': {
        'enabled': True,
        'description': 'List the assets available',
        'usage_example': 'show me the list of assets',
        'examples': [
            "which assets exist",
            "list the assets",
            "list which assets exist",
            "show the assets",
            "show the asset list",
            "show which assets exist",
            "display the assets",
            "display the asset list",
            "display which assets exist",
        ],
    },
    'selected-asset': {
        'enabled': True,
        'description': 'Select an asset for this room',
        'usage_example': 'activate the asset {asset name}',
        'examples': [
            "activate asset",
            "active asset"
            "select the asset",
            "set as the active asset",
            "set as the current asset",
            "set this room's asset to",
            "update this room's asset to",
            "the current asset is",
            "the new asset is",
            "update the asset to",
            "change the asset to",
        ],
    },
    'auto-analysis': {
        'enabled': True,
        'description': 'Run an analysis on a curve',
        'usage_example': 'run an analysis on {curve name}',
        'examples': [
            'analyse',
            'analyse the mnemonic',
            'analyse the curve',
            'analyse mnemonic',
            'analyse curve',
            'run an analysis on',
            'execute an analysis on',
            'can you analyse the mnemonic',
            'can you analyse the curve',
            'can you run an analysis on',
            'can you execute an analysis on',
        ],
    },
    'pipes-current-value': {
        'enabled': False,
        'description': 'Returns the current value for a mnemonic',
        'usage_example': 'what is the current value for {curve name}',
        'examples': [
            'curve',
            'mnemonic',
            'current value',
            'what the value',
            'what value does habe',
            'you know the value',
            'you know what is the value',
        ]
    },
    'bot-features': {
        'examples': [
            '/help',
            '!help',
            '/commands',
            '!commands',
            'list your features',
            'which features  have',
            'which tasks can perform',
            'how can you help me',
            'how can you help us',
            'what can you do',
            'what can be done you',
            'what is your job',
            'how can you help me',
            'what are you capable',
            'which capabilities do you have',
            'which powers do you have',
            'what is your superpower',
            'which are your superpowers'
            'which superpowers do you have',
        ],
    },
}

NEGATIVE_EXAMPLES = [
    'good evening',
    'good morning',
    'good afternoon',
    "what's up",
    'what is the value',
    'hey what value does it',
    'do you know the value',
    'do you know what is the value',
    'it is time to go to sleep',
    'what is your favorite color',
    'what the color of the sky',
    'i had a great time',
    'thyme is my favorite herb',
    'do you have time to look at my essay',
    'how do you have the time to do all this'
    'what is it',
]


FEATURES_DESCRIPTION_TEMPLATE = """My features are:
{% for feature_data in features %}
  *{{ feature_data.description }}*
  Try: _"{{ bot_name }}, {{ feature_data.usage_example }}"_
{% endfor %}
"""
