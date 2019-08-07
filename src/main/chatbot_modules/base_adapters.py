# -*- coding: utf-8 -*-
from chatterbot.logic import LogicAdapter
from chatterbot.conversation import Statement

__all__ = ['BaseBayesAdapter']


class BaseBayesAdapter(LogicAdapter):
    """
    Superclass for adapters using naive bayes
    """
    positive_examples = []
    negative_examples = []
    confidence_threshold = 0.75

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
        return self.classifier.classify(my_features)

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
        return confidence > self.confidence_threshold


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
