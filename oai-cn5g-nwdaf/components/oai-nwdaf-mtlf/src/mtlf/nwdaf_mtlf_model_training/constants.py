"""Shared experiment defaults for the IDS/NWDAF research code.

These values mirror the current constants in the legacy ``IDS_lib.py`` module,
but this module has no PyTorch or dataset-loading side effects.
"""

from __future__ import annotations


DEFAULT_NUM_CLASSES = 6
CLASS_NAMES = ("normal", "coapdos", "mqttflood", "pingflood", "portscan", "tcpsyn")
DEFAULT_NUM_REGIONS = 5

DEFAULT_BATCH_SIZE = 16
DEFAULT_SEQUENCE_LEN = 256
DEFAULT_PACKET_LEN = 1500

DEFAULT_EPOCHS = 50
DEFAULT_DISTILLATION_EPOCHS = 25
DEFAULT_LEARNING_RATE = 0.0001
DEFAULT_DELTA_LOSS = 0.001
DEFAULT_STUDENT_TEMPERATURE = 1
DEFAULT_DISTILLATION_ALPHA = 0.1

