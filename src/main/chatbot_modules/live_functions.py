# -*- coding: utf-8 -*-
from functools import partial
from uuid import uuid4

from chatterbot.conversation import Statement
from eliot import start_action

from live_client.assets import run_analysis
from live_client.events import annotation
from live_client.events.constants import TIMESTAMP_KEY
from live_client.utils.timestamp import get_timestamp

from .base_adapters import BaseBayesAdapter, NLPAdapter, WithAssetAdapter
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


class AutoAnalysisAdapter(BaseBayesAdapter, NLPAdapter, WithAssetAdapter):
    """
    Analyze a curve on live
    """

    state_key = 'auto-analysis'
    index_curve = 'ETIM'
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

        self.room_id = kwargs['room_id']
        self.analyzer = partial(
            run_analysis,
            process_name,
            process_settings,
            output_info
        )
        self.annotator = partial(
            annotation.create,
            process_settings=process_settings,
            output_info=output_info,
        )

    def find_index_value(self, statement):
        tagged_words = self.pos_tag(statement)

        # Find out where the {index_curve} was mentioned
        # and look for a number after the mention
        value = None
        index_mentioned = False
        for word, tag in tagged_words:
            if word == self.index_curve:
                index_mentioned = True

            if index_mentioned and (tag == 'CD'):  # CD: Cardinal number
                value = word
                break

        return value

    def run_analysis(self, asset, curve, begin=None, duration=30000, confidence=0):
        if begin is None:
            begin = get_timestamp() - duration

        end = begin + duration

        analysis_results = self.analyzer(
            assetId="{0[asset_type]}/{0[asset_id]}".format(asset),
            channel=curve,
            qualifier=curve,
            computeFields=self.default_state.get('computeFields'),
            begin=begin,
            end=end,
        )

        if analysis_results:
            # Gerar annotation
            analysis_results.update(
                __src='auto-analysis',
                uid=str(uuid4()),
                createdAt=get_timestamp(),
                room={'id': self.room_id}
            )
            with start_action(action_type='create annotation', curve=curve):
                self.annotator(
                    '{} for {}'.format(self.state_key, curve),
                    analysis_results,
                )

            response_text = "Analysis of curve {} finished".format(curve)
            confidence = 1  # Otherwise another answer might be chosen

        else:
            response_text = "Analysis of curve {} returned no data".format(curve)

        return response_text, confidence

    def run_query(self, asset, curve, index_value, confidence=0):
        selected_asset = self.get_selected_asset()
        if selected_asset:
            asset_config = selected_asset.get('asset_config', {})

            value_query = '''
            {event_type} .flags:nocount .flags:reversed
            => {{{target_curve}}}:map():json() as {{{target_curve}}},
               {{{index_curve}}}->value as {{{index_curve}}}
            => @filter({{{index_curve}}}#:round() == {index_value})
            '''.format(
                event_type=asset_config['filter'],
                target_curve=curve,
                index_curve=self.index_curve,
                index_value=index_value,
            )

            return super().run_query(
                value_query,
                realtime=False,
                span="since ts 0 #partial='1'",
                callback=partial(
                    self.prepare_analysis,
                    asset=asset,
                    curve=curve,
                    index_value=index_value,
                    confidence=confidence,
                )
            )

    def prepare_analysis(self, content, asset=None, curve=None, index_value=None, confidence=0):
        if not content:
            response_text = 'No information about {curve} at {index_curve} {index_value}'.format(
                curve=curve,
                index_curve=self.index_curve,
                index_value=index_value,
            )

        else:
            for item in content:
                timestamp = int(item.get(TIMESTAMP_KEY, 0)) or None

                with start_action(action_type=self.state_key, curve=curve, begin=timestamp):
                    response_text, confidence = self.run_analysis(
                        asset,
                        curve,
                        begin=timestamp,
                        confidence=confidence
                    )

        return response_text, confidence

    def process_direct_analysis(self, statement, selected_asset, confidence=0, begin=None):
        selected_curves = self.find_selected_curves(statement)
        num_selected_curves = len(selected_curves)

        if num_selected_curves == 1:
            selected_curve = selected_curves[0]

            ##
            # Iniciar analise
            with start_action(action_type=self.state_key, curve=selected_curve):
                response_text, confidence = self.run_analysis(
                    selected_asset,
                    selected_curve,
                    confidence=confidence
                )

        elif num_selected_curves == 0:
            response_text = "I didn't get the curve name. Can you repeat please?"

        else:
            response_text = "I'm sorry, which of the curves you want to analyse?{}{}".format(
                ITEM_PREFIX,
                ITEM_PREFIX.join(selected_curves)
            )

        return response_text, confidence

    def process_indexed_analysis(self, statement, selected_asset, confidence=0):
        selected_curves = self.find_selected_curves(statement)
        num_selected_curves = len(selected_curves)
        selected_value = self.find_index_value(statement)

        if selected_value is None:
            response_text = "I didn't get which ETIM value you want me to use as reference."

        elif num_selected_curves == 0:
            response_text = "I didn't get the curve name. Can you repeat please?"

        elif num_selected_curves == 1:
            selected_curve = selected_curves[0]

            with start_action(action_type=self.state_key, curve=selected_curve):
                response_text, confidence = self.run_query(
                    selected_asset,
                    selected_curve,
                    selected_value,
                    confidence=confidence,
                )

        else:
            response_text = "I'm sorry, which of the curves you chose?{}{}".format(
                ITEM_PREFIX,
                ITEM_PREFIX.join(selected_curves)
            )

        return response_text, confidence

    def process(self, statement, additional_response_selection_parameters=None):
        confidence = self.get_confidence(statement)

        if confidence > self.confidence_threshold:
            self.load_state()
            selected_asset = self.get_selected_asset()

            if selected_asset is None:
                response_text = "No asset selected. Please select an asset first."
            else:
                mentioned_curves = self.list_mentioned_curves(statement)
                has_index_mention = (
                    (len(mentioned_curves) > 1) and (self.index_curve in mentioned_curves)
                )

                if has_index_mention:
                    response_text, confidence = self.process_indexed_analysis(
                        statement,
                        selected_asset,
                        confidence=confidence
                    )

                else:
                    response_text, confidence = self.process_direct_analysis(
                        statement,
                        selected_asset,
                        confidence=confidence
                    )

            response = Statement(text=response_text)
            response.confidence = confidence
        else:
            response = None

        return response
