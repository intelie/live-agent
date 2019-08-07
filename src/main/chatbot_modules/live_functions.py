# -*- coding: utf-8 -*-
from datetime import datetime
from chatterbot.conversation import Statement

from utils import logging

from .base_adapters import BaseBayesAdapter
from .constants import (
    AUTO_ANALYSIS_EXAMPLES,
    NEGATIVE_EXAMPLES,
    ASSET_LIST_EXAMPLES,
    ASSET_SELECTION_EXAMPLES
)

"""
  curl 'http://localhost:8080/services/plugin-liverig-vis/auto-analysis/analyse?asset=ReplayRig3&assetId=rig%2F19&channel=QDPRESS_PQ2%20-%20MRPQ%202%20Quartzdyne%20Pressure&qualifier=QDPRESS_PQ2&begin=1564586600270&end=1564586797098&computeFields=min&computeFields=max&computeFields=avg&computeFields=stdev&computeFields=linreg&computeFields=derivatives' \
      -H 'Pragma: no-cache'
      -H 'DNT: 1'
      -H 'Accept-Encoding: gzip, deflate, br'
      -H 'Accept-Language: en-US,en;q=0.9'
      -H 'User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.145 Safari/537.36 Vivaldi/2.6.1566.49'
      -H 'Accept: application/json, text/plain, */*'
      -H 'Live-TimeZone: America/Sao_Paulo'
      -H 'Referer: http://localhost:8080/'
      -H 'Cookie: BAYEUX_BROWSER=7bqhdoqtjnb6lz7v; LIVERIGSESSIONID=9ohmdxaw46pazn20qa421sps; csrftoken=beJXZmRaPTpjS5jqHVsvVS8Y4x6iAjlV; remember-me=YWRtaW46MTU2NDc1ODgwMzEzNTpkNzNhM2Q4NjVkZTdhYjNjYzk0MDQ2YjYzYTg5ZTk4MA; __login=; JSESSIONID=m2wfcgb4nlit1rvaln9sy8tr5'  # NOQA
      -H 'Connection: keep-alive'
      -H 'Cache-Control: no-cache'
      --compressed


  path:
      /services/plugin-liverig-vis/auto-analysis/analyse

  parâmetros:
      - asset (não é usado no código)
      - assetId
      - channel
      - qualifier
      - begin
      - end
      - computeFields


  exemplo:
      <- bot, analyze QDPRESS between 4:15:00 and 4:16:10
      -> Vitor: Ok, what is your timezone?
      <- bot, it is BRT
      -> análise
"""


__all__ = ['AutoAnalysisAdapter']


class AutoAnalysisAdapter(BaseBayesAdapter):
    """
    Analyze a curve on live
    """

    state_key = 'auto-analysis'
    required_state = [
        'assetId',
        'channel',
        'qualifier',
        'begin',
        'end',
        'computeFields',
    ]
    default_state = {
        'computeFields': ['min', 'max', 'avg', 'stdev', 'linreg', 'derivatives']
    }
    positive_examples = AUTO_ANALYSIS_EXAMPLES
    negative_examples = NEGATIVE_EXAMPLES + ASSET_LIST_EXAMPLES + ASSET_SELECTION_EXAMPLES

    def process(self, statement, additional_response_selection_parameters=None):
        state = additional_response_selection_parameters.get(
            self.state_key, self.default_state
        )

        logging.info('Search text for {}: {}'.format(statement, statement.search_text))
        now = datetime.now()

        time_features = self.analyze_features(statement.text.lower())
        confidence = self.classifier.classify(time_features)
        response = Statement(text='The current time is ' + now.strftime('%I:%M %p'))

        response.confidence = confidence
        response.state = state
        return response
