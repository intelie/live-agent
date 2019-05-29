# -*- coding: utf-8 -*-
from enum import Enum

"""
Description:

Detect when the pumps are activated, then:
- When only one pump is active: notify pumping rate changes;
- When both pumps are activated in an interval larger than 30 seconds: notify pumping rate changes for each pump;
- When both pumps are activated in a 30 seconds interval: notify pumping rate changes, commingled flow, focused flow and bottle filling;


Possible alarms:
- The duration of a commingled flow is too short (< 3 mins?)
- Motor speed steady, pumping rates dropped and pressure risen: probable seal loss

Examples:
- https://shellgamechanger.intelie.com/#/dashboard/54/?mode=view&span=2019-05-28%252009%253A54%253A21%2520to%25202019-05-28%252012%253A50%253A44  # NOQA
- http://localhost:8080/#/dashboard/21/?mode=view&span=2019-05-28%252011%253A36%253A05%2520to%25202019-05-28%252013%253A07%253A28%2520%2520shifted%2520right%2520by%252025%2525  # NOQA


Possible states:

ID      DESCRIPTION                                                         Pump 1 state        Pump 2 state        Sampling state
------------------------------------------------------------------------------------------------------------------------------------
0.0     No sampling                                                         INACTIVE            INACTIVE            INACTIVE

1.0     Pump N activated at ETIM with flow rate X, pressure Y               PUMPING             INACTIVE            INACTIVE
1.1     Pump N rate changed to X at ETIM with pressure Y                    PUMPING             INACTIVE            INACTIVE
1.2     Pump N deactivated at ETIM with pressure Y                          BUILDUP_EXPECTED    INACTIVE            INACTIVE

2.0     Buildup stabilized within 0.1 at ETIM with pressure X               BUILDUP_STABLE      INACTIVE            INACTIVE
2.1     Buildup stabilized within 0.01 at ETIM with pressure X              INACTIVE            INACTIVE            INACTIVE

3.0     Commingled flow started at ETIM with pressures X and Y (rate X/Y)   PUMPING             PUMPING             COMMINGLED_FLOW
3.0a    Alert: Commingled flow too short?                                   INACTIVE            INACTIVE            INACTIVE
3.1     Outer pump rate changed to X at ETIM with pressure Y                PUMPING             PUMPING             COMMINGLED_FLOW
         or Pump N rate changed to X at ETIM with pressure Y
3.2     Focused flow started at ETIM with pressures X and Y (rate X/Y)      PUMPING             PUMPING             FOCUSED_FLOW

4.0     Bottle filling start at ETIM with pressure X                        PUMPING             INACTIVE            SAMPLING
4.0a    Alert: Motor speed and flow rate diverging. Lost seal?              PUMPING             PUMPING             FOCUSED_FLOW
4.1     Bottle filling end at ETIM with pressure X                          PUMPING             PUMPING             FOCUSED_FLOW

3.3     Focused flow finished at ETIM with pressures X and Y (rate X/Y)     BUILDUP_EXPECTED    BUILDUP_EXPECTED    INACTIVE


State transitions:

         |
         |
         v
    --> 0.0 --> 1.0 -> 1.1 -> 1.2 ---------    --------------------
    |       |    |             ^          |    ^       ^          |
    |       |    |             |          v    |       |          |
    |       |    ---------------    ---> 2.0 --> 2.1 ---          |
    |       |                       |                             |
    |       |         ---> 3.0a -----                             |
    |       |         |                                           |
    |       --> 3.0 --|--------> 3.2 --------------------> 3.3 ---|
    |                 |           ^     |                         |
    |                 ---> 3.1 ---|     |     --> 4.0a -----      |
    |                             |     |     |            |      |
    |                             |     ---> 4.0 --> 4.1 --|      |
    |                             |                        |      |
    |                             --------------------------      |
    |                                                             |
    ---------------------------------------------------------------

"""

PUMP_STATES = Enum(
    'PUMP_STATES',
    'INACTIVE, PUMPING, BUILDUP_EXPECTED, BUILDUP_STABLE'
)
SAMPLING_STATES = Enum(
    'SAMPLING_STATES',
    'INACTIVE, COMMINGLED_FLOW, FOCUSED_FLOW, SAMPLING'
)
