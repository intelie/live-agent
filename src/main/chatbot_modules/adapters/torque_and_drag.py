import queue
import re

from chatterbot.conversation import Statement
from eliot import start_action
from live_client.events.constants import EVENT_TYPE_EVENT, EVENT_TYPE_DESTROY
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
def @custom_batch():
    list(*) every ((*->timestamp# - (*->timestamp#:prev ?? *->timestamp#))>10) before => @for => @yield;
def convert_to_custom_unit(mnemonic, uom, value):
    curve_unit_force_convert(value#, uom, mnemonic:decode("DBTM", "m","HKLA", "N", "MFIA", "m3/s"));

-- getting tripping in data
va007_trip_out .timestamp:adjusted_index_timestamp mnemonic!:(WOBA|DMEA|RPMA|ROPA|DBTM|MFIA|BPOS|HKLA)
-- @@lookup.rig_event_type .timestamp:adjusted_index_timestamp mnemonic!:(WOBA|DMEA|RPMA|ROPA|DBTM|MFIA|BPOS|HKLA)

-- => @meta @@lookup.span_by_rig_name[0]?? @@userspan as span
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

        min_depth = params['min_depth']
        max_depth = params['max_depth']
        start_time = params['start_time']
        end_time = params['end_time']

        # Build pipes query:
        query = (tnd_query_template
            .replace('{min_depth}', min_depth)
            .replace('{max_depth}', max_depth)
            .replace('{start_time}', start_time)
            .replace('{end_time}', end_time)
        )

        # Execute pipes query:
        result = self.run_query(
            query,
            realtime = False,
            span = '2018-02-12 10:00 to 2018-02-13 09:20',
            callback = lambda res: res,
        )

        '''
        results_process, results_queue = self.query_runner(
            query,
            realtime = True,
            span = '2018-02-12 10:00 to 2018-02-13 09:20'
        )

        result = 'Ainda não foi :(' # <<<<<
        try:
            event = results_queue.get(timeout=self.query_timeout)
            event_data = event.get('data', {})
            event_type = event_data.get('type')
            if event_type == EVENT_TYPE_EVENT:
                result = event_data.get('content', [])
            #elif event_type != EVENT_TYPE_DESTROY:
            #    continue

        except queue.Empty as e:
            logging.exception(e)

        results_process.join(10)
        '''

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

        #message = '\n'.join(message_lines)
        message = result

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


    def run_query(self, query_str, realtime=False, span=None, callback=None):
        with start_action(action_type=self.state_key, query=query_str):
            results_process, results_queue = self.query_runner(
                query_str,
                realtime=realtime,
                span=span,
            )

            result = []
            i = 1 #<<<<<
            while True:
                try:
                    print(f'Passagem {i}') #<<<<<
                    i += 1 #<<<<<
                    event = results_queue.get(timeout=self.query_timeout)
                    event_data = event.get('data', {})
                    event_type = event_data.get('type')
                    print(event_type) #<<<<<
                    if event_type == EVENT_TYPE_EVENT:
                        result = event_data.get('content', [])
                        print(result) #<<<<<
                    elif event_type != EVENT_TYPE_DESTROY:
                        continue


                except queue.Empty as e:
                    logging.exception(e)

                results_process.join(1)
                return callback(result)
