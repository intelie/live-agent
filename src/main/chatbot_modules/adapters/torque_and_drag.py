import re

from chatterbot.conversation import Statement
from eliot import start_action
from live_client.utils import logging
from multiprocessing import Process
from process_modules import PROCESS_HANDLERS

from .base import (
    BaseBayesAdapter,
    WithAssetAdapter
)
from ..constants import (
    get_positive_examples,
    get_negative_examples,
)


tnd_query_template = """
-- custom functions
def @custom_batch():list(*) every ((*->timestamp# - (*->timestamp#:prev ?? *->timestamp#))>10) before => @for => @yield;
def convert_to_custom_unit(mnemonic, uom, value):
   curve_unit_force_convert(value#, uom, mnemonic:decode("DBTM", "m","HKLA", "N", "MFIA", "m3/s"));
-- getting tripping in data
va007_trip_out .timestamp:adjusted_index_timestamp mnemonic!:(WOBA|DMEA|RPMA|ROPA|DBTM|MFIA|BPOS|HKLA)
-- making batch of data and calculating opmode
=> @custom_batch
=> expand normalized_operating_mode(timestamp#, mnemonic, value#,  uom, 'WOBA', 'DMEA', 'RPMA', 'ROPA',
'DBTM', 'MFIA', 'BPOS', 'HKLA'), map(mnemonic, convert_to_custom_unit(mnemonic, uom, value)) as values every batch
-- filtering by opmode
=> @filter operating_mode != null && operating_mode != 'Connection' && operating_mode != 'Drilling Connection' && operating_mode != 'Tripping Connection'
-- filtering by bit depth value
=> @filter values['DBTM'] >= {min_depth}
=> @filter values['DBTM'] < {max_depth}
-- filtering by low hook load values
=> @filter values['HKLA'] > 900000
-- printing data
=> newmap('flowRate', values['MFIA'], 'hookLoad', values['HKLA'], 'bitDepth', values['DBTM'])
=> @yield
"""

class TorqueAndDragAdapter(WithAssetAdapter, BaseBayesAdapter):
    state_key = 'torque-drag'
    #required_state = [
    #    'assetId',
    #]
    #default_state = {
    #    'active_monitors': {}
    #}
    positive_examples = get_positive_examples(state_key)
    negative_examples = get_negative_examples(state_key)

    def __init__(self, chatbot, **kwargs):
        super().__init__(chatbot, **kwargs)

        self.process_settings = kwargs['process_settings']
        self.helpers = dict(
            (name, func)
            for (name, func) in kwargs.get('functions', {}).items()
            if '_state' not in name
        )

        self.all_monitors = self.process_settings.get('monitors', {})


    def process(self, statement, additional_response_selection_parameters=None):
        #Verify if the message is for us to process:
        #example = 'calibrate torque and drag for bitdepth until 4300m from 9:00 to 9:30'
        keywords = 'torque,drag'.split(',')
        #min_depth = 0
        #max_depth = ??
        #start_time = ??
        #end_time = ??

        # Not ours, move on:
        found_keywords = [word for word in statement.text.lower().split() if word in keywords]
        if sorted(found_keywords) != sorted(keywords):
            response = Statement('')
            response.confidence = 0
            return response

        # Extract parameters from message:
        confidence = 1
        params = self._get_calibration_params(statement.text)
        if params == None:
            response = Statement("Sorry, I can't read the calibration parameters from your message")
            response.confidence = confidence
            return response

        # Build pipes query:
        # Execute pipes query
        # Build calibration request:
        # Request calibration data
        # Define output:
        message_lines = [
            'Performing calibration with parameters:',
            f'Min Bitdepth:{params["min_depth"]}m,',
            f'Max Bitdepth:{params["max_depth"]}m,',
            f'Start Time: {params["start_time"]},',
            f'End Time: {params["end_time"]}',
        ]
        calibration_response_lines =  [
            'Calibration output: ',
            'travellingBlockWeight = 789000',
            'pipesWeightMultiplier = 0.87',
        ]
        message_lines.append('')
        message_lines.extend(calibration_response_lines)

        message = '\n'.join(message_lines)

        response = Statement(message)
        response.confidence = confidence

        return response


    def _get_calibration_params(self, message):
        ret = None
        m = re.search(r'(\d+).+?(\d+).+?(\d{1,2}:\d{2}).+?(\d{1,2}:\d{2})\s*$', message)
        if m != None:
            ret = {
                'min_depth': m.group(1),
                'max_depth': m.group(2),
                'start_time': m.group(3),
                'end_time': m.group(4),
            }
        return ret
