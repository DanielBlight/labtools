#!/usr/bin/env python3
import CryostationComm
import time
from time import sleep
from decimal import Decimal


# This is an example that demonstrates external communication with a Cryostation.  It is not intended to 
# be a production worthy python script.

# This script sends commands to the Cryostation to retrieve data (get) or to set system values (set).

def get_idle_state(cryostation_connection):
    """Get the current idle state,  GIS=Get Idle State"""

    success = False
    state = False
    try:
        state = cryostation_connection.send_command_get_response("GIS").startswith("T")
        success = True
    except Exception as err:
         print("Failed to get idle state")
   
    return success, state

def get_nitrogen_state(cryostation_connection):
    """Get the current system nitrogen state,  GNS=Get Nitrogen State"""
    
    success = False
    state = False
    try:
        state = cryostation_connection.send_command_get_response("GNS").startswith("T")
        success = True
    except Exception as err:
         print("Failed to get system nitrogen state")
        
    return success, state

def get_platform_temperature(cryostation_connection):
    """Get the current platform temperature, GPT=Get Platform Temperature"""
    
    success = False
    reply = ''
    temperature = 0.0
    try:
        reply = cryostation_connection.send_command_get_response("GPT")
        try:
            temperature = Decimal(reply)
            success  = True
        except Exception as err:
            print("Failed to read platform temperature")
    except Exception as err:
         print("Failed to get platform temperature")

    return success, temperature
	
def get_stage1_temperature(cryostation_connection):
    """Get the current stage 1 temperature, GS1T=Get Stage 1 Temperature"""
    
    success = False
    reply = ''
    temperature = 0.0
    try:
        reply = cryostation_connection.send_command_get_response("GS1T")
        try:
            temperature = Decimal(reply)
            success  = True
        except Exception as err:
            print("Failed to read stage 1 temperature")
    except Exception as err:
         print("Failed to get stage 1 temperature")

    return success, temperature

def get_stage2_temperature(cryostation_connection):
    """Get the current stage 2 temperature, GS2T=Get Stage 2 Temperature"""
    
    success = False
    reply = ''
    temperature = 0.0
    try:
        reply = cryostation_connection.send_command_get_response("GS2T")
        try:
            temperature = Decimal(reply)
            success  = True
        except Exception as err:
            print("Failed to read stage 2 temperature")
    except Exception as err:
         print("Failed to get stage 2 temperature")

    return success, temperature

def get_chamber_pressure(cryostation_connection):
    """Get the current chamber pressure, GCP=Get Chamber Pressure"""
    
    success = False
    reply = ''
    pressure = 0.0
    try:
        reply = cryostation_connection.send_command_get_response("GCP")
        try:
            pressure = Decimal(reply)
            success  = True
        except Exception as err:
            print("Failed to read chamber pressure")
    except Exception as err:
         print("Failed to get chamber pressure")
        
    return success, pressure

def set_target_platform_temperature(cryostation_connection, set_point, timeout = 10):
    "Set the target platform temperature."

    print("Set target platform temperature {0}".format(set_point))

    timeout = time.time() + timeout  # Determine timeout

    target_temperature = send_target_platform_temperature(cryostation_connection, set_point)
    while round(target_temperature, 2) != round(set_point, 2):
        if timeout > 0:
            if time.time() > timeout:  # If we pass the timeout, give up.
                return False
        sleep(1)
        target_temperature = send_target_platform_temperature(cryostation_connection, set_point)

    return True

def send_target_platform_temperature(cryostation_connection, set_point):
    "Send the target platform temperature to the Cryostation.  Read it back to verify the set operation.  STSP=Set Target Set Point.  GTSP=Get Target Set Point"

    print("Send target platform temperature {0}".format(set_point))

    temp_set_point = 0.0
    reply = ''
    try:
        if cryostation_connection.send_command_get_response("STSP" + str(set_point)).startswith("OK"):
            reply = cryostation_connection.send_command_get_response("GTSP")
            try:
                temp_set_point = Decimal(reply)
            except Exception as err:
                print("Failed to set target platform temperature")
    except Exception as err:
        print("Failed to send target platform temperature")

    return temp_set_point

def set_platform_PID_state(cryostation_connection, state):
    "Set the platform PID on/off.  SPP=Set Platform Pid."

    print("Set platform PID state {0}".format(state))

    success = False
    try:
        if cryostation_connection.send_command_get_response("SPP" + str(state)[:1]).startswith("OK"):
            success = True
        else:
            print("Platform state failed")
    except Exception as err:
        print("Failed to set platform state")

    return success

def set_vent_valve_state(cryostation_connection, state):
    "Set the vent valve open/closed. SVV=Set Vent Valve"

    print("Set vent valve state {0}".format(state))

    strState = 'C'           # Closed
    if state is True:
        strState = 'O'       # Open
    success = False
    try:
        if cryostation_connection.send_command_get_response("SVV" + strState).startswith("OK"):    # SVV=Set Vent Value
            success = True
        else:
            print("Vent valve state failed")
    except Exception as err:
        print("Failed to set vent valve state")

    return success

def set_case_valve_state(cryostation_connection, state):
    "Set the case valve open/closed. SCV=Set Case Valve"

    print("Set case valve state {0}".format(state))

    strState = 'C'           # Closed
    if state is True:
        strState = 'O'       # Open
    success = False
    try:
        if cryostation_connection.send_command_get_response("SCV" + strState).startswith("OK"):    # SCV=Set Case Value.
            success = True
        else:
            print("Case valve state failed")
    except Exception as err:
        print("Failed to set case valve state")

    return success

def set_vacuum_pump_state(cryostation_connection, state):
    "Set the vacuum pump on/off. SVP=Set Vacuum Pump"

    print("Set vacuump pump state {0}".format(state))

    strState = 'S'           # Stopped
    if state is True:
        strState = 'R'       # Running
    success = False
    try:
        if cryostation_connection.send_command_get_response("SVP" + strState).startswith("OK"):    # SVP=Set Vacuum Pump.
            success = True
        else:
            print("Vacuum pump state failed")
    except Exception as err:
        print("Failed to set vacuum pump state")

    return success
