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
        'description': 'List the assets available',
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
        'description': 'Select an asset for this room',
        'examples': [
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
        'description': 'Run an analysis on a curve',
        'examples': [
            'analyse a mnemonic',
            'analyse a curve',
            'run an analysis',
            'execute an analysis',
            'can you analyse a mnemonic',
            'can you analyse a curve',
            'can you run an analysis',
            'can you execute an analysis',
        ],
    },
    'bot-features': {
        'examples': [
            '/help',
            '!help',
            '/commands',
            '!commands',
            'list your features',
            'which features do you have',
            'which tasks can you perform',
            'how can you help me',
            'how can you help us',
            'what can you do',
            'what can be done by you',
            'what is your job',
            'how can you help me',
            'what are you capable of',
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


FEATURES_DESCRIPTION_TEMPLATE = """
My features are:
{% for feature_data in features %}
  *{{ feature_data.description }}*
  Try saying: _{{ bot_name }}: {{ feature_data.examples|random }}_
{% endfor %}
"""
