# -*- coding: utf-8 -*-
from chatterbot.logic import LogicAdapter

__all__ = ['BaseBayesAdapter']


class BaseBayesAdapter(LogicAdapter):
    """
    Superclass for adapters using naive bayes
    """

    state_key = None
    required_state = []
    default_state = {}
    positive_examples = []
    negative_examples = []

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
