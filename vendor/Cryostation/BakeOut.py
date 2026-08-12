#!/usr/bin/env python3
import CryostationComm
import Commands as Commands
from Common import dtprint
from EntryConditionsMet import entryConditionsMet
import time
from time import sleep


# *******************************
#           WARNING
# *******************************
# DO NOT EXECUTE THIS SCRIPT IF the system has added excess N-grease on the components or if components have been 
# added to the chamber that will be damaged by a temperature of 350K.  Original Montana Instrument components can 
# withstand this temperature. 
# *******************************

# This is an example that demonstrates external communication with a Cryostation.  It is not intended to 
# be a production worthy python script.
#
# This script performs a system bake out to remove contaminants from the system.
# Returns True if the bake out completed successfully, False otherwise.
#
# Performing a bake out, heating the chamber, will re-activate the charcoal in the system and help drive water 
# from sample space surfaces.

def bake_out(cryostation_connection, check_entry_conditions=True, temperature=350, timeout = 3600, duration = 3600):
                                                                  # temperature (K), timeout (s), duration (s)
    if check_entry_conditions:
        dtprint("Check entry conditions")
        if not entryConditionsMet(cryostation_connection):
            dtprint("System is not ready for bake out process.")
            exit(1)

    timeout = time.time() + timeout  # Determine temperature timeout

    dtprint("Start bake out")

    # Entry actions
    if not Commands.set_vent_valve_state(cryostation_connection, False):  # Close vent valve
        return False
    if not Commands.set_vacuum_pump_state(cryostation_connection, True):  # Start vacuum pump
        return False
    if not Commands.set_case_valve_state(cryostation_connection, True):   # Open case valve
        return False

    dtprint("Set bake out target temperature.")
    if not Commands.set_target_platform_temperature(cryostation_connection, temperature):
        dtprint("Bake out target temperature, {0}, not set.".format(temperature))
        return False

    dtprint("Turn platform PID on.")
    if not Commands.set_platform_PID_state(cryostation_connection, True):   # Turn on the platform PID
        dtprint("Platform PID not set.".format(temperature))
        return False

    # Achieve back out temperature
    dtprint("Wait for bake out target temperature.")
    passed = False
    while time.time() < timeout and not passed:
        sleep(1)
        have_temp, current_temp = Commands.get_platform_temperature(cryostation_connection)
        passed = have_temp and current_temp >= temperature

    if not passed:
        dtprint("Bake out target temperature, {0}, not achieved.".format(temperature))
        return False
    else:
        dtprint("Bake out target temperature achieved")

    # Bake out
    dtprint("Baking for {0} seconds.".format(duration))
    sleep(duration)
    dtprint("Finished baking.")

    # Exit actions
    if not Commands.set_platform_PID_state(cryostation_connection, False):         # Turn off platform PID
        return False
    if not Commands.set_target_platform_temperature(cryostation_connection, 2):    # Set target temperature to 2K
        return False
    if not Commands.set_case_valve_state(cryostation_connection, False):           # Close case valve
        return False
    if not Commands.set_vacuum_pump_state(cryostation_connection, False):          # Stop vacuum pump
        return False
    
    dtprint("Bake out passed = {0}".format(passed))
    return True
