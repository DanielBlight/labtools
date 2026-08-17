import pyvisa

ADDRESS = "USB0::0x1313::0x804A::M00739898::INSTR"
SAFE_TEST_CURRENT_A = 0.050

rm = pyvisa.ResourceManager()
itc = rm.open_resource(ADDRESS)

itc.timeout = 5000
itc.write_termination = "\n"
itc.read_termination = "\n"

def query(command):
    response = itc.query(command).strip()
    print(f"{command:<18} -> {response}")
    return response

def write_and_check(command):
    print(f"WRITE              -> {command}")
    itc.write(command)
    query("*OPC?")
    query("SYST:ERR?")

try:
    query("*IDN?")
    write_and_check("*CLS")

    query("SOUR:CURR?")
    query("OUTP?")
    query("OUTP2?")

    write_and_check(f"SOUR:CURR {SAFE_TEST_CURRENT_A}")
    query("SOUR:CURR?")

    write_and_check("OUTP2 ON")
    query("OUTP2?")

    # Leave LD output off during the initial diagnostic.
finally:
    try:
        itc.write("OUTP OFF")
    except Exception:
        pass
    itc.close()
    rm.close()
