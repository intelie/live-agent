import json
import queue
import re
import requests

from chatterbot.conversation import Statement
from eliot import start_action
from live_client.events.constants import EVENT_TYPE_EVENT, EVENT_TYPE_DESTROY
from live_client.utils import logging
from utils.util import attempt

from .base import BaseBayesAdapter, WithAssetAdapter
from ..constants import get_positive_examples, get_negative_examples


def build_statement(text, confidence):
    statement = Statement(text)
    statement.confidence = confidence
    return statement


def build_handler_statement(confidence, handler, params = None):
    return build_statement(build_handler_call_str(handler, params), confidence)


tnd_query_template = """
-- custom functions
def @custom_batch():
    list(*) every (
      (*->timestamp# - (*->timestamp#:prev ?? *->timestamp#)) > 10
    ) before
    => @for
    => @yield;

def convert_to_custom_unit(mnemonic, uom, value):
    curve_unit_force_convert(value#, uom, mnemonic:decode("DBTM", "m","HKLA", "N", "MFIA", "m3/s"));

-- getting tripping in data
{event_type} .timestamp:adjusted_index_timestamp mnemonic!:(WOBA|DMEA|RPMA|ROPA|DBTM|MFIA|BPOS|HKLA)

-- making batch of data and calculating opmode
=> @custom_batch
=> expand
  normalized_operating_mode(
    timestamp#, mnemonic, value#, uom,
    'WOBA', 'DMEA', 'RPMA', 'ROPA', 'DBTM', 'MFIA', 'BPOS', 'HKLA'
  ),
  map(mnemonic, convert_to_custom_unit(mnemonic, uom, value)) as values,
  lookup.rig_event_type_well_id.get(__type) as well_id
  every batch

-- filtering by opmode
=> @filter
  operating_mode != null
  && operating_mode != 'Connection'
  && operating_mode != 'Drilling Connection'
  && operating_mode != 'Tripping Connection'

-- filtering by bit depth value
=> @filter values['DBTM'] >= {min_depth}
=> @filter values['DBTM'] < {max_depth}

-- filtering by low hook load values
=> @filter values['HKLA'] > 900000

-- printing data
=> newmap('flowRate', values['MFIA'], 'hookLoad', values['HKLA'], 'bitDepth', values['DBTM'], 'wellId', well_id)
=> @yield
"""


class TorqueAndDragAdapter(WithAssetAdapter, BaseBayesAdapter):
    state_key = "torque-drag"
    positive_examples = get_positive_examples(state_key)
    negative_examples = get_negative_examples(state_key)

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)

        self.process_settings = kwargs["process_settings"]
        self.live_host = self.process_settings["live"]["host"]
        self.username = self.process_settings["live"]["username"]
        self.password = self.process_settings["live"]["password"]

        self.helpers = dict(
            (name, func)
            for (name, func) in kwargs.get("functions", {}).items()
            if "_state" not in name
        )

    def process(self, statement, additional_response_selection_parameters=None):
        # Try to read params from the chat:
        confidence = self.get_confidence(statement)
        params = self.extract_calibration_params(statement.text)
        if not params:
            return build_handler_statement(confidence, handle_cant_read_params, params)

        # Parameters read, so we believe it's ours.
        confidence = 1

        # Do we have a selected asset?
        asset = self.get_selected_asset()
        if asset == {}:
            return build_handler_statement(confidence, handle_no_asset_selected, params)
        params["event_type"] = self.get_event_type(asset)

        return build_handler_statement(confidence, handle_perform_calibration, params)

    def can_process(self, statement):
        keywords = ["torque", "drag"]
        found_keywords = [word for word in statement.text.lower().split() if word in keywords]
        has_required_terms = sorted(found_keywords) == sorted(keywords)
        return has_required_terms and super().can_process(statement)

    # TODO: Melhorar a maneira de obter os parâmetros para ficar mais fácil para o usuário:
    def extract_calibration_params(self, message):
        # NOTE: Eu usaria o mesmo mecanismo de `EtimQueryAdapter.find_index_value`
        ret = None
        m = re.search(
            r"(\d+).+?(\d+).+?(\d{4}-\d\d-\d\d \d{1,2}:\d{2}).+?(\d{4}-\d\d-\d\d \d{1,2}:\d{2})\s*$",
            message,
        )
        if m is not None:
            return {
                "min_depth": m.group(1),
                "max_depth": m.group(2),
                "start_time": m.group(3),
                "end_time": m.group(4),
            }

        m = re.search(r"(\d+) *m *and *(\d+) *m.*?$", message)
        if m is not None:
            return {"min_depth": m.group(1), "max_depth": m.group(2)}


class TorqueAndDragCalibrator:

    query_timeout = 60

    def __init__(self, liveclient):
        self.liveclient = liveclient
        self.process_settings = liveclient.process_settings
        self.live_host = self.process_settings["live"]["host"]
        self.username = self.process_settings["live"]["username"]
        self.password = self.process_settings["live"]["password"]


    def run_query(self, query_str, realtime=False, span=None, callback=None):
        #results_process, results_queue = self.query_runner(query_str, realtime=realtime, span=span)
        results_process, results_queue = self.liveclient.run_query(query_str, realtime=realtime, span=span)

        result = []
        while True:
            try:
                event = results_queue.get(timeout=self.query_timeout)
                event_data = event.get("data", {})
                event_type = event_data.get("type")
                if event_type == EVENT_TYPE_EVENT:
                    result.extend(event_data.get("content", []))

                if event_type == EVENT_TYPE_DESTROY:
                    break

            except queue.Empty as e:
                logging.exception(e)

        results_process.join(1)

        if callback is not None:
            return callback(result)
        return result

    def build_calibration_data(self, well_id, travelling_block_weight, points):
        return {
            "wellId": well_id,
            "travellingBlockWeight": travelling_block_weight,
            "saveResult": "true",
            "calibrationMethod": "LINEAR_REGRESSION",
            "points": points,
        }

    def request_calibration(self, well_id, points):
        service_path = "/services/plugin-og-model-torquendrag/calibrate/"
        url = f"{self.live_host}{service_path}"

        s = requests.Session()
        s.auth = (self.username, self.password)
        travelling_block_weight = (
            0
        )  # This value is ignored for LINEAR_REGRESSION (the only supported right now)
        calibration_data = self.build_calibration_data(well_id, travelling_block_weight, points)
        response = s.post(url, json=calibration_data)
        try:
            response.raise_for_status()
        except Exception as e:
            logging.exception(e)
            raise

        result = response.json()
        return result

    def live_retrieve_regression_points(self, params):
        points = []
        pipes_query = tnd_query_template.format(
            event_type=params["event_type"],
            min_depth=params["min_depth"],
            max_depth=params["max_depth"],
        )

        start_time = params["start_time"]
        end_time = params["end_time"]
        span = f"{start_time} to {end_time}"
        points = self.run_query(pipes_query, span=span)
        return points

    def live_timestamps_from_depth_range(self, event_type, depth_range, span=None):
        span = span or "since ts 0 #partial='1'"
        template = "{event_type} mnemonic!:DBTM value#:{depth_range} .timestamp:adjusted_index_timestamp .flags:reversed"

        candidates = []
        pipes_query = template.format(event_type=event_type, depth_range=str(depth_range))
        candidates = self.run_query(pipes_query, span=span)
        return candidates

    def infer_time_range(self, params):
        RANGE_SIZE = 100
        min_depth = int(params["min_depth"])
        max_depth = int(params["max_depth"])
        event_type = params["event_type"]
        start_depth_range = [min_depth, min_depth + RANGE_SIZE]
        end_depth_range = [max_depth - RANGE_SIZE, max_depth]

        end_ts = self.retrieve_timestamp_for_depth_range(
            max, end_depth_range, event_type, error_message="Could not infer a value for end_ts."
        )

        start_ts = self.retrieve_timestamp_for_depth_range(
            min,
            start_depth_range,
            event_type,
            error_message="Could not infer a value for start_ts.",
            span=f"since ts 0 until ts {end_ts} #partial='1'",
        )

        end_ts = (
            attempt(
                self.retrieve_timestamp_for_depth_range,
                max,
                end_depth_range,
                event_type,
                error_message="Could not infer a value for end_ts.",
                span=f"since ts {start_ts} until ts {end_ts} #partial='1'",
            )
            or end_ts
        )

        params.update(start_time=f"ts {start_ts}", end_time=f"ts {end_ts}")

    def retrieve_timestamp_for_depth_range(
        self, fn, depth_range, event_type, *, error_message, span=None
    ):
        try:
            candidates = self.live_timestamps_from_depth_range(event_type, depth_range, span=span)
            timestamp = fn(map(lambda val: int(val["timestamp"]), candidates))
        except:
            raise Exception(error_message)
        return timestamp


    def build_success_response(self, context):
        message = f"""Calibration Results:
-  Well ID: {context["wellId"]}
-  Regression method: {context["calibration_result"]["calibrationMethod"]}
-  Travelling Block Weight: {context["calibration_result"]["travellingBlockWeight"]}
-  Pipes Weight Multiplier: {context["calibration_result"]["pipesWeightMultiplier"]}
"""
        response = Statement(message)
        return response


# TODO: Mover 'build_handler_call_str' para um lugar comum a todos os adapters (ou chatbot).  <<<<<
def build_handler_call_str(handler, params = None):
    fn_fully_qualified_name = f"{handler.__module__}.{handler.__name__}"
    fn_params = json.dumps(params or {})
    return f"::{fn_fully_qualified_name}\n{fn_params}"


#TODO: Handlers should return a string and not a Statement <<<<<
def handle_cant_read_params(params, liveclient):
    message = "Sorry, I can't read the calibration parameters from your message"
    print(f"[Collateral Effect - handle_cant_read_params]: {message}.")
    return Statement(message)


def handle_no_asset_selected(params, liveclient):
    message = "Please, select an asset before performing the calibration"
    print(f"[Collateral Effect - handle_no_asset_selected]: {message}.")
    return Statement(message)


def handle_perform_calibration(params, liveclient):
    calibrator = TorqueAndDragCalibrator(liveclient)

    # Gather all needed data to retrieve the data points:
    MIN_POINT_COUNT = 2
    if params.get("start_time") == None:
        try:
            calibrator.infer_time_range(params)
        except Exception as e:
            return Statement(f"{str(e)} Please select another range.")

    # Retrieve the points to calculate the regression:
    points = calibrator.live_retrieve_regression_points(params)
    if len(points) < MIN_POINT_COUNT:
        return Statement(
            "There are not enough data points to perform the calibration. Please select another range."
        )
    well_id = points[0]["wellId"]

    # Perform calibration:
    try:
        calibration_result = calibrator.request_calibration(well_id, points)
    except:
        return Statement("I'm not able to get data from calibration service. Please, check dda and live configuration.")

    # Return a response:
    response = calibrator.build_success_response({
        "wellId": well_id,
        "calibration_result": calibration_result
    })
    return response
