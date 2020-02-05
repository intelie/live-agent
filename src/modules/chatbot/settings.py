# -*- coding: utf-8 -*-

##
# Logic adapter registry used by the `bot-features` adapter
FEATURES = {
    "asset-list": {"enabled": True},
    "selected-asset": {"enabled": True},
    "auto-analysis": {"enabled": True},
    "etim-query": {"enabled": True},
    "current-query": {"enabled": True},
    "monitor-control": {"enabled": True},
    "torque-drag": {"enabled": True},
    "bot-features": {},
}


NEGATIVE_EXAMPLES = [
    "good evening",
    "good morning",
    "good afternoon",
    "what's up",
    "what is the value",
    "hey what value does it",
    "do you know the value",
    "do you know what is the value",
    "it is time to go to sleep",
    "what is your favorite color",
    "what the color of the sky",
    "i had a great time",
    "thyme is my favorite herb",
    "do you have time to look at my essay",
    "how do you have the time to do all this" "what is it",
]
