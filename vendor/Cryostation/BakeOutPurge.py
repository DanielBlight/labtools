#!/usr/bin/env python3
import CryostationComm
import Commands as Commands
from Common import dtprint
from EntryConditionsMet import entryConditionsMet
import BakeOut as BakeOut
import Purge as Purge


# *******************************
#           WARNING
# *******************************
# DO NOT EXECUTE THIS SCRIPT IF the system has added excess N-grease on the components or if components have been 
# added to the chamber that will be damaged by a temperature of 350K.  Original Montana Instrument components can 
# withstand this temperature. 
# *******************************

# This is an example that demonstrates external communication with a Cryostation.  It is not intended to 
# be a production worthy python script.

# This script performs a system bake out and purge to clear the system of contaminants.
#
# Performing a bake out, heating the chamber, will re-activate the charcoal in the system and help drive water 
# from sample space surfaces.
#
# Performing a system purge, pumping down to 10 Torr and purging with nitrogen multiple times, is a great 
# way to help remove water vapor and ultimately end up with a more successful pump down. Once the 
# system is down to 10 Torr, flushing dry nitrogen into the chamber will impart energy into the water 
# molecules through the collisions with the nitrogen and help to knock them off the walls and  
# radiation shield. This helps to remove water and improve base pressure. 


# User defined parameters:  Modify these parameter values for the specific Cryostation under operation.

cryostation_ip   = "192.168.0.15"                     # Cryostation IP address
cryostation_port = 7773                               # Cryostation external control port from the PREFERENCES tabpage


# Process parameters:  Do not modify these parameters without considering and understanding the affects to the system.

minimum_temperature = 285                             # Minimum temperature (K) system must be above in order to perform bake out purge
medium_vacuum_pressure = 300000                       # Target pressure (mTorr) used during leak test
bake_out_temperature = 350                            # Bake out target temperature (K)
bake_out_temperature_timeout = 3600                   # Maximum time (s) to reach bake out temperature.  1 hour
bake_out_duration = 3600                              # Bake out duration (s). 1 hour
pump_down_pressure = 10000                            # Pump down target pressure (mTorr)
pump_down_timeout = 120                               # Maximum time (s) to pump down to the pump down pressure. 2 minutes
purge_duration = 3                                    # Purge duration (s)


def stop_system(cryostation_connection):
    Commands.set_vacuum_pump_state(cryostation_connection, False)   # Stop vacuum pump
    Commands.set_vent_valve_state(cryostation_connection, False)    # Close vent valve
    Commands.set_case_valve_state(cryostation_connection, False)    # Close case valve
    Commands.set_platform_PID_state(cryostation_connection,  False) # Turn off the platform PID

if __name__ == "__main__":

    dtprint("BAKE OUT PURGE")

    # Establish Cryostation communication
    try:
        cryostation_connection = CryostationComm.CryoComm(cryostation_ip, cryostation_port)
    except:
        dtprint("Could not connect to Cryostation IP: {0}, Port: {1}".format(cryostation_ip, cryostation_port))
        exit(1)

    print("\n")
    dtprint("CHECK ENTRY CONDITIONS")
    if not entryConditionsMet(cryostation_connection, minimum_temperature, medium_vacuum_pressure):
        dtprint("System is not ready for bake out purge process.")
        exit(1)

    print("\n")
    dtprint("BAKE OUT")
    if not BakeOut.bake_out(cryostation_connection, False, bake_out_temperature, bake_out_temperature_timeout, bake_out_duration):
        dtprint("Bake out was not successfull.  Purge process will not be performed.")
        stop_system(cryostation_connection)
        exit(1)

    print("\n")
    dtprint("SYSTEM PURGE")
    if not Purge.system_purge(cryostation_connection, False, pump_down_pressure, pump_down_timeout, purge_duration):
        dtprint("Purge was not successfull.")
        stop_system(cryostation_connection)
        exit(1)

    print("\n")
    dtprint("STOP SYSTEM")
    stop_system(cryostation_connection)

    print("\n")
    dtprint("DONE")
