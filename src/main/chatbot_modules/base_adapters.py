# -*- coding: utf-8 -*-
from pprint import pformat
from chatterbot.logic import LogicAdapter
from chatterbot.conversation import Statement
from eliot import start_action
import nltk

from live_client.assets.utils import only_enabled_curves
from utils import logging

__all__ = []


class BaseBayesAdapter(LogicAdapter):
    """
    Superclass for adapters using naive bayes
    """
    positive_examples = []
    negative_examples = []
    confidence_threshold = 0.75
    confidence_damping_thresold = 0.9

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)

        from nltk import NaiveBayesClassifier

        self.positive = kwargs.get('positive', self.positive_examples)
        self.negative = kwargs.get('negative', self.negative_examples)

        labeled_data = (
            [
                (name, 0) for name in self.negative
            ] + [
                (name, 1) for name in self.positive
            ]
        )

        train_set = [
            (self.analyze_features(text), n) for (text, n) in labeled_data
        ]

        self.classifier = NaiveBayesClassifier.train(train_set)

    def analyze_features(self, text):
        """
        Provide an analysis of significant features in the string.
        """
        features = {}

        # A list of all words from the known sentences
        all_words = " ".join(self.positive + self.negative).split()

        # A list of the first word in each of the known sentence
        all_first_words = []
        for sentence in self.positive + self.negative:
            all_first_words.append(
                sentence.split(' ', 1)[0]
            )

        for word in text.split():
            features['first_word({})'.format(word)] = (word in all_first_words)

        for word in text.split():
            features['contains({})'.format(word)] = (word in all_words)

        for letter in 'abcdefghijklmnopqrstuvwxyz':
            features['count({})'.format(letter)] = text.lower().count(letter)
            features['has({})'.format(letter)] = (letter in text.lower())

        return features

    def get_confidence(self, statement):
        my_features = self.analyze_features(statement.text.lower())
        return self.classifier.classify(my_features) * self.confidence_damping_thresold

    def process(self, statement, additional_response_selection_parameters=None):
        confidence = self.get_confidence(statement)

        response = Statement(
            text="{}: {}, confidence={}".format(
                self.__class__.__name__, statement.search_text, confidence
            )
        )

        self.confidence = response.confidence = confidence
        return response

    def can_process(self, statement):
        confidence = self.get_confidence(statement)
        can_process = confidence > self.confidence_threshold

        logging.debug("{} (confidence {}): The 10 most informative features are: {}".format(
            self.__class__.__name__,
            confidence,
            ", ".join(
                pformat(item)
                for item in self.classifier.most_informative_features(n=10)
            )
        ))

        return can_process


class NLPAdapter(LogicAdapter):

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)
        self.download_and_log('maxent_ne_chunker')
        self.download_and_log('words')

    def download_and_log(self, name):
        logging.info(f"Downloading {name}")
        nltk.download(name)

    def tokenize(self, statement):
        return nltk.word_tokenize(statement.text)

    def pos_tag(self, statement):
        tokens = self.tokenize(statement)
        return nltk.pos_tag(tokens)


class WithStateAdapter(LogicAdapter):
    """
    Superclass for adapters requiring an internal state per conversation
    """

    state_key = None
    required_state = []
    default_state = {}

    def __init__(self, chatbot, **kwargs):
        functions = kwargs.get('functions', {})
        if ('load_state' not in functions) or ('share_state' not in functions):
            raise ValueError('Cannot keep state without a reference to state management functions')

        self.__state = None
        self.__shared_state = None
        self._load_state = functions['load_state']
        self._share_state = functions['share_state']

        super().__init__(chatbot, **kwargs)

    def load_state(self):
        self.__shared_state = self._load_state(
            state_key=self.state_key,
            default=self.default_state
        )
        self.__state = self.__shared_state[self.state_key]

    def share_state(self):
        self._share_state(
            state_key=self.state_key,
            state_data=self.state
        )

    @property
    def shared_state(self):
        if not self.__shared_state:
            self.load_state()

        return self.__shared_state

    @property
    def state(self):
        return self.__state

    @state.setter
    def state(self, new_state):
        self.__state = new_state


class WithAssetAdapter(WithStateAdapter):

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)
        self.query_runner = kwargs.get('functions', {})['run_query']

    def get_selected_asset(self):
        return self.shared_state.get('selected-asset', {})

    def get_asset_curves(self, asset):
        all_curves = asset.get('asset_config', {}).get('curves', {})
        return only_enabled_curves(all_curves)

    def curve_was_mentioned(self, curve, statement, exact=True, match_case=True):
        statement_text = statement.text

        if match_case is False:
            statement_text = statement_text.upper()
            curve = curve.upper()

        text_words = statement_text.split()
        if exact:
            result = any(
                filter(lambda word: curve == word, text_words)
            )
        else:
            result = curve in statement_text

        return result

    def list_mentioned_curves(self, statement):
        selected_asset = self.get_selected_asset()
        curves = self.get_asset_curves(selected_asset)

        # First, try a more lenient search
        mentions = dict(
            (item, {'exact': False})
            for item in curves
            if self.curve_was_mentioned(item, statement, exact=False, match_case=False)
        )

        # Then try to find an exact mention of the curves
        mentions.update(
            dict(
                (item, {'exact': True})
                for item in curves
                if self.curve_was_mentioned(item, statement, exact=True)
            )
        )
        return mentions

    def find_selected_curves(self, statement):
        index_curve = getattr(self, 'index_curve', None)

        if index_curve is None:
            mentioned_curves = self.list_mentioned_curves(statement)
        else:
            mentioned_curves = dict(
                (name, data)
                for name, data in self.list_mentioned_curves(statement).items()
                if name != index_curve
            )

        # Try to find an exact mention to a curve
        selected_curves = [
            name for name, match_data in mentioned_curves.items()
            if match_data.get('exact') is True
        ]

        # Failing that, use all matches
        if not selected_curves:
            selected_curves = list(mentioned_curves.keys())

        return selected_curves

    def run_query(self, query_str, realtime=False, span=None, callback=None):
        with start_action(action_type=self.state_key, query=query_str):
            results_process, results_queue = self.query_runner(
                query_str,
                realtime=realtime,
                span=span,
            )

            result = []
            while True:
                event = results_queue.get()
                event_data = event.get('data', {})
                event_type = event_data.get('type')
                if event_type == 'event':
                    result = event_data.get('content', [])
                elif event_type != 'stop':
                    continue

                return callback(result)
