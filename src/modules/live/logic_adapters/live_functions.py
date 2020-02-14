# -*- coding: utf-8 -*-
from functools import partial
from uuid import uuid4
from eliot import start_action
from chatterbot.conversation import Statement

from live_client.assets import run_analysis
from live_client.events import annotation
from live_client.events.constants import TIMESTAMP_KEY
from live_client.utils.timestamp import get_timestamp

from chatbot.actions import CallbackAction
from chatbot.logic_adapters.base import BaseBayesAdapter, NLPAdapter, WithAssetAdapter
from ..constants import ITEM_PREFIX


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


__all__ = ["AutoAnalysisAdapter"]


class AutoAnalysisAdapter(BaseBayesAdapter, NLPAdapter, WithAssetAdapter):
    """
    Analyze a curve on live
    """

    state_key = "auto-analysis"
    index_curve = "ETIM"
    required_state = ["assetId", "channel", "begin", "end", "computeFields"]
    default_state = {"computeFields": ["min", "max", "avg", "stdev", "linreg", "derivatives"]}
    positive_examples = [
        "analyse",
        "analyse mnemonic",
        "analyse curve",
        "analyse mnemonic",
        "analyse curve",
        "run an analysis on",
        "execute an analysis on",
        "can you analyse mnemonic",
        "can you analyse curve",
        "can you run an analysis on",
        "can you execute an analysis on",
    ]
    description = "Run an analysis on a curve"
    usage_example = "run an analysis on {curve name} [after ETIM 1500]"

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)
        settings = kwargs.get("settings", {})
        self.annotator = partial(annotation.create, settings=settings)

        self.room_id = kwargs["room_id"]
        self.analyzer = partial(run_analysis)

    def find_index_value(self, statement):
        tagged_words = self.pos_tag(statement)

        # Find out where the {index_curve} was mentioned
        # and look for a number after the mention
        value = None
        index_mentioned = False
        for word, tag in tagged_words:
            if word == self.index_curve:
                index_mentioned = True

            if index_mentioned and (tag == "CD"):  # CD: Cardinal number
                value = word
                break

        return value

    def run_analysis(self, asset, curve, begin=None, duration=30000):
        if begin is None:
            begin = get_timestamp() - duration

        end = begin + duration

        analysis_results = self.analyzer(
            assetId="{0[asset_type]}/{0[asset_id]}".format(asset),
            channel=curve,
            qualifier=curve,
            computeFields=self.default_state.get("computeFields"),
            begin=begin,
            end=end,
        )

        if analysis_results:
            # Gerar annotation
            analysis_results.update(
                __src="auto-analysis",
                uid=str(uuid4()),
                createdAt=get_timestamp(),
                room={"id": self.room_id},
            )
            with start_action(action_type="create annotation", curve=curve):
                self.annotator(analysis_results)

            response_text = "Analysis of curve {} finished".format(curve)

        else:
            response_text = "Analysis of curve {} returned no data".format(curve)

        return response_text

    def run_query(self, asset, curve, index_value):
        selected_asset = self.get_selected_asset()
        if selected_asset:
            asset_config = selected_asset.get("asset_config", {})

            value_query = """
            {event_type} .flags:nocount .flags:reversed
            => {{{target_curve}}}:map():json() as {{{target_curve}}},
               {{{index_curve}}}->value as {{{index_curve}}}
            => @filter({{{index_curve}}}#:round() == {index_value})
            """.format(
                event_type=asset_config["filter"],
                target_curve=curve,
                index_curve=self.index_curve,
                index_value=index_value,
            )

            return super().run_query(
                value_query,
                realtime=False,
                span="since ts 0 #partial='1'",
                callback=partial(
                    self.prepare_analysis, asset=asset, curve=curve, index_value=index_value
                ),
            )

    def prepare_analysis(self, content, asset=None, curve=None, index_value=None):
        if not content:
            response_text = "No information about {curve} at {index_curve} {index_value}".format(
                curve=curve, index_curve=self.index_curve, index_value=index_value
            )

        else:
            for item in content:
                timestamp = int(item.get(TIMESTAMP_KEY, 0)) or None

                with start_action(action_type=self.state_key, curve=curve, begin=timestamp):
                    response_text = self.run_analysis(asset, curve, begin=timestamp)

        return response_text

    def process_direct_analysis(self, statement, selected_asset, begin=None):
        selected_curves = self.find_selected_curves(statement)
        num_selected_curves = len(selected_curves)

        if num_selected_curves == 1:
            selected_curve = selected_curves[0]

            ##
            # Iniciar analise
            with start_action(action_type=self.state_key, curve=selected_curve):
                response_text = self.run_analysis(selected_asset, selected_curve)

        elif num_selected_curves == 0:
            response_text = "I didn't get the curve name. Can you repeat please?"

        else:
            response_text = "I'm sorry, which of the curves you want to analyse?{}{}".format(
                ITEM_PREFIX, ITEM_PREFIX.join(selected_curves)
            )

        return response_text

    def process_indexed_analysis(self, statement, selected_asset):
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
                response_text = self.run_query(selected_asset, selected_curve, selected_value)

        else:
            response_text = "I'm sorry, which of the curves you chose?{}{}".format(
                ITEM_PREFIX, ITEM_PREFIX.join(selected_curves)
            )

        return response_text

    def can_process(self, statement):
        return "analys" in statement.text.lower()

    def process(self, statement, additional_response_selection_parameters=None):
        confidence = self.get_confidence(statement)

        if confidence > self.confidence_threshold:
            # [ECS]: Essa chamada é necessária para chamar 'get_selected_asset' ? Se for ver um modo melhor de garantir esse passo.  # NOQA
            self.load_state()
            selected_asset = self.get_selected_asset()
            if selected_asset == {}:
                response_text = "No asset selected. Please select an asset first."
            else:
                return CallbackAction(
                    self.perform_analysis,
                    confidence,
                    statement=statement,
                    selected_asset=selected_asset,
                )

            response = Statement(text=response_text)
            response.confidence = confidence
        else:
            response = None

        return response

    def perform_analysis(self, statement, selected_asset):
        mentioned_curves = self.list_mentioned_curves(statement)
        has_index_mention = (len(mentioned_curves) > 1) and (self.index_curve in mentioned_curves)

        processor = (
            self.process_indexed_analysis if has_index_mention else self.process_direct_analysis
        )
        response_text = processor(statement, selected_asset)
        return response_text
