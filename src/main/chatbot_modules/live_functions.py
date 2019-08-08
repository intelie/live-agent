# -*- coding: utf-8 -*-
from functools import partial
from chatterbot.conversation import Statement

from live_client.assets import run_analysis
from live_client.assets.utils import only_enabled_curves

from .base_adapters import BaseBayesAdapter, WithStateAdapter
from .constants import get_positive_examples, get_negative_examples

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

ITEM_PREFIX = '\n  '


class AutoAnalysisAdapter(BaseBayesAdapter, WithStateAdapter):
    """
    Analyze a curve on live
    """

    state_key = 'auto-analysis'
    required_state = [
        'assetId',
        'channel',
        'begin',
        'end',
        'computeFields',
    ]
    default_state = {
        'computeFields': ['min', 'max', 'avg', 'stdev', 'linreg', 'derivatives']
    }
    positive_examples = get_positive_examples(state_key)
    negative_examples = get_negative_examples(state_key)

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)

        process_name = kwargs['process_name']
        process_settings = kwargs['process_settings']
        output_info = kwargs['output_info']

        self.analyzer = partial(
            run_analysis,
            process_name,
            process_settings,
            output_info
        )

    def get_selected_asset(self):
        return self.shared_state.get('selected-asset')

    def get_asset_curves(self, asset):
        all_curves = asset.get('asset_config', {}).get('curves', {})
        return only_enabled_curves(all_curves)

    def process(self, statement, additional_response_selection_parameters=None):
        self.confidence = self.get_confidence(statement)

        def curve_was_mentioned(curve):
            return curve in statement.text

        if self.confidence > self.confidence_threshold:
            self.load_state()
            selected_asset = self.get_selected_asset()
            if selected_asset is None:
                response_text = "No asset selected. Please select an asset first."
            else:
                curves = self.get_asset_curves(selected_asset)
                selected_curves = list(
                    filter(curve_was_mentioned, curves)
                )

                if len(selected_curves) == 1:
                    selected_curve = selected_curves[0]
                    response_text = "Ok, analysing curve {}".format(selected_curve)

                    ##
                    # Iniciar analise
                    # Gerar annotation

                elif len(selected_curves) > 1:
                    response_text = "I didn't understand, which of the curves you chose?{}{}".format(
                        ITEM_PREFIX,
                        ITEM_PREFIX.join(selected_curves)
                    )

                else:
                    response_text = "I didn't get the curve name. Can you repeat please?"

            response = Statement(text=response_text)
            response.confidence = self.confidence
        else:
            response = None

        return response
