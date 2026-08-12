#!/usr/bin/env python3
import CryostationComm
import Commands as Commands
from Common import dtprint
from EntryConditionsMet import entryConditionsMet
import time
from time import sleep


# This is an example that demonstrates external communication with a Cryostation.  It is not intended to 
# be a production worthy python script.

# This script performs the pump down and nitrogen purge process to remove contaminants from the system.
# Returns True if the pump down and nitrogen purge completed successfully, False otherwise.
#
# Before cooling down, execute the pump down and nitrogen purge process. Pumping down to 10 Torr and purging 
# with nitrogen multiple times is a great way to help remove water vapor and ultimately end up with a 
# more successful pump down. Once the system is down to 10 Torr, flushing dry nitrogen into the chamber will 
# impart energy into the water molecules through the collisions with the nitrogen and help to knock 
# them off the walls and radiation shield. This helps to remove water and improve base pressure. 


def system_purge(cryostation_connection, check_entry_conditions=True, pressure=10000, pump_down_timeout=120, purge_duration=3):
                                                                      # pressure (mTorr), pump_down_timeout (s), purge_duration (s)
    if check_entry_conditions:
        dtprint("Check entry conditions")
        if not entryConditionsMet(cryostation_connection):
            dtprint("System is not ready for purge process.")
            exit(1)

    dtprint("Start system purge")

    # Entry actions
    if not Commands.set_vent_valve_state(cryostation_connection, False):  # Close vent valve
        return False

    # Perform the pump down purge process three times.
    for i in range(3):
        if not pump_down(cryostation_connection, pressure, pump_down_timeout):
            return False
        if not purge(cryostation_connection, purge_duration):
            return False

    # Finish with the pump down process
    if not pump_down(cryostation_connection, pressure, pump_down_timeout):
            return False

    dtprint("System purge passed = True")
    return True

def pump_down(cryostation_connection, pressure=10000, timeout=120):

    dtprint("Start pump down")

    # Entry actions
    if not Commands.set_vacuum_pump_state(cryostation_connection, True):  # Start vacuum pump
        return False
    if not Commands.set_case_valve_state(cryostation_connection, True):   # Open case valve
        return False

    timeout = time.time() + timeout  # Determine timeout

    # Pump down the system to the target pressure within the timeout
    dtprint("Wait for pump down pressure.")
    passed = False
    while time.time() < timeout and not passed:
        sleep(1)
        have_pressure, current_pressure = Commands.get_chamber_pressure(cryostation_connection)
        passed = have_pressure and current_pressure <= pressure

    # Exit actions
    if not Commands.set_case_valve_state(cryostation_connection, False):   # Close case valve
        return False
    if not Commands.set_vacuum_pump_state(cryostation_connection, False):  # Stop vacuum pump
        return False

    dtprint("Pump down passed = {0}".format(passed))
    return passed

def purge(cryostation_connection, duration=3):

    dtprint("Start purge")

    # Entry actions
    if not Commands.set_vent_valve_state(cryostation_connection, True):  # Open vent valve
        return False
    if not Commands.set_case_valve_state(cryostation_connection, True):  # Open case valve
        return False

    duration = time.time() + duration  # Determine duration

    # If nitrogen is present, purge the system for the specified duration
    have_state, state = Commands.get_nitrogen_state(cryostation_connection)
    passed = have_state and state
    while time.time() < duration and passed:
        sleep(1)
        have_state, state = Commands.get_nitrogen_state(cryostation_connection)
        passed = have_state and state

    dtprint("Purge finished")

    # Exit actions
    if not Commands.set_case_valve_state(cryostation_connection, False):  # Close case valve
        return False
    if not Commands.set_vent_valve_state(cryostation_connection, False):  # Close vent valve
        return False
		
    dtprint("Purge passed = {0}".format(passed))
    return passed
