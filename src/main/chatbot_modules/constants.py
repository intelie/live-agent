# -*- coding: utf-8 -*-

__all__ = [
    'get_positive_examples',
    'get_negative_examples',
]

ITEM_PREFIX = '\n  '

LOGIC_ADAPTERS = [
    {
        'import_path': 'chatterbot.logic.BestMatch',
        'default_response': 'I am sorry, but I do not understand.',
        'maximum_similarity_threshold': 0.90
    },
    'chatbot_modules.internal.StateDebugAdapter',
    'chatbot_modules.internal.AdapterReloaderAdapter',
    'chatbot_modules.internal.BotFeaturesAdapter',
    'chatbot_modules.live_asset.AssetListAdapter',
    'chatbot_modules.live_asset.AssetSelectionAdapter',
    'chatbot_modules.live_functions.AutoAnalysisAdapter',
    'chatbot_modules.pipes_query.EtimQueryAdapter',
    'chatbot_modules.pipes_query.CurrentValueQueryAdapter',
    'chatbot_modules.monitors.MonitorControlAdapter',
]


##
# Logic adapter registry used by the `bot-features` adapter
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
            "show the assets list",
            "show which assets exist",
            "display the assets",
            "display the assets list",
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
            "select asset",
            "set active asset",
            "set current asset",
            "set this room's asset",
            "update this room's asset",
            "current asset is",
            "new asset is",
            "update asset to",
            "change asset to",
        ],
    },
    'auto-analysis': {
        'enabled': True,
        'description': 'Run an analysis on a curve',
        'usage_example': 'run an analysis on {curve name} [after ETIM 1500]',
        'examples': [
            'analyse',
            'analyse mnemonic',
            'analyse curve',
            'analyse mnemonic',
            'analyse curve',
            'run an analysis on',
            'execute an analysis on',
            'can you analyse mnemonic',
            'can you analyse curve',
            'can you run an analysis on',
            'can you execute an analysis on',
        ],
    },
    'etim-query': {
        'enabled': True,
        'description': 'Query the value for a curve at an specific ETIM value',
        'usage_example': 'what is the value for {curve name} at ETIM 1500?',
        'examples': [
            'value at ETIM',
            'what value for when ETIM',
        ],
    },
    'current-query': {
        'enabled': True,
        'description': 'Query the most recent value for a curve',
        'usage_example': 'what is the current value for {curve name}?',
        'examples': [
            'current value',
            'value now',
        ],
    },
    'monitor-control': {
        'enabled': True,
        'description': 'Start the monitors',
        'usage_example': 'start the monitors',
        'examples': [
            'start monitor',
            'initialize monitor',
            'run monitor',
        ],
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


##
# Example phrases for the naive bayes based adapters
def get_positive_examples(key):
    return FEATURES[key]['examples']


def get_negative_examples(key):
    examples = NEGATIVE_EXAMPLES
    for feature_key, feature_data in FEATURES.items():
        if feature_key != key:
            examples.extend(feature_data.get('examples', []))

    return examples


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
