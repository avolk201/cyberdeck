import serial
import serial.tools.list_ports
import time

ports = list(serial.tools.list_ports.comports())
nano_port = None
for p in ports:
    if "Arduino" in p.description or "Nano" in p.description or "USB" in p.description:
        nano_port = p.device
        break

if not nano_port:
    print("Could not find Nano!")
    import sys; sys.exit(1)

print(f"Connecting to {nano_port}...")
s = serial.Serial(nano_port, 115200, timeout=1)
time.sleep(2) # wait for bootloader

print("Sending S MC_NETRUNNER_HUD")
s.write(b"S MC_NETRUNNER_HUD\n")
s.flush()

for i in range(10):
    line = s.readline()
    if line:
        print("Nano says:", line.decode(errors='ignore').strip())

s.write(b"S MC_SYSTEM_VITALS\n")
s.flush()
print("Sent S MC_SYSTEM_VITALS")
time.sleep(1)
