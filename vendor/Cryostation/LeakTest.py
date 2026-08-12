#!/usr/bin/env python3
import CryostationComm
import Commands as Commands
from Common import dtprint
import time
from time import sleep


# This is an example that demonstrates external communication with a Cryostation.  It is not intended to 
# be a production worthy python script.

# This script tests for major leaks in the system.
# Returns True if no major leak is detected.  Returns False if a major leak is detected.

def leak_test(cryostation_connection, medium_vac = 300000, timeout = 120):    # medium_vac (mTorr), timeout (s)
    """
    Pull medium vacuum to ensure no major leak exists. Returns True
    if the medium_vac pressure level was reached within the time
    limit, False otherwise.
    """

    dtprint("Start leak test, target pressure {0} mTorr, timeout {1} s".format(medium_vac, timeout))

    timeout = time.time() + timeout  # Determine timeout

    # Entry actions
    if not Commands.set_vent_valve_state(cryostation_connection, False):  # Close vent valve
        return False
    if not Commands.set_vacuum_pump_state(cryostation_connection, True):  # Start vacuum pump
        return False
    if not Commands.set_case_valve_state(cryostation_connection, True):   # Open case valve
        return False

    # Monitor pressure to determine if target pressure reached before timeout.
    passed = False
    while time.time() < timeout and not passed:
        sleep(1)
        have_pressure, current_pressure = Commands.get_chamber_pressure(cryostation_connection)
        passed = have_pressure and current_pressure <= medium_vac

    dtprint("Finish leak test")

    # Exit actions
    if not Commands.set_case_valve_state(cryostation_connection, False):   # Close case valve
        return False
    if not Commands.set_vacuum_pump_state(cryostation_connection, False):  # Stop vacuum pump
        return False
    
    dtprint("Leak test passed = {0}".format(passed))

    return passed
