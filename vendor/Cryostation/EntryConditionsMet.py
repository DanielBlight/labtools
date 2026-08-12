#!/usr/bin/env python3
import CryostationComm
import Commands as Commands
from Common import dtprint
import LeakTest as LeakTest


# This is an example that demonstrates external communication with a Cryostation.  It is not intended to 
# be a production worthy python script.

# This script checks the entry conditions required for the bake out purge processes.
# Returns True if the conditions are met, False otherwise.

def entryConditionsMet(cryostation_connection, min_temp=285, leak_test_pressure=300000):    # min_temp (K), leak_test_pressure (mTorr)
    "Verify the system is in a acceptable state for the bake out purge process"

    dtprint("Checking entry conditions")

    # System must be idle/stopped, not in automatic mode
    have_state, state = Commands.get_idle_state(cryostation_connection)
    if not have_state or not state:
        dtprint("System not in an idle state")
        return False

    # System must be warm
    have_temp, temperature = Commands.get_platform_temperature(cryostation_connection)
    if not have_temp or temperature <= min_temp:
        dtprint("System not warm")
        return False
    have_temp, temperature = Commands.get_stage1_temperature(cryostation_connection)
    if not have_temp or temperature <= min_temp:
        dtprint("System not warm")
        return False
    have_temp, temperature = Commands.get_stage2_temperature(cryostation_connection)
    if not have_temp or temperature <= min_temp:
        dtprint("System not warm")
        return False

    # Nitrogen must be present
    have_state, state = Commands.get_nitrogen_state(cryostation_connection)
    if not have_state or not state:
        dtprint("System does not have nitrogen")
        return False

    dtprint("System idle, warm, and nitrogen present.")

    # Check for major leaks
    dtprint("Start leak test")
    if not LeakTest.leak_test(cryostation_connection, leak_test_pressure):
        dtprint("Leak detected.")
        return False
    dtprint("Finished leak test")

    dtprint("Check entry conditions passed = True")
    return True
