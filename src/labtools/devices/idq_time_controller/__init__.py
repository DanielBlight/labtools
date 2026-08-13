"""IDQuantique Time Controller device wrapper package.

Public API is re-exported here so existing imports keep working:

    from labtools.devices.idq_time_controller import IDQTimeController
"""

from labtools.devices.idq_time_controller.controller import IDQTimeController

__all__ = ["IDQTimeController"]
