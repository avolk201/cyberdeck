import random

LINES = [
    "Breach attempt detected...",
    "Bypassing ICE...",
    "Memory allocated: 0x4F2A",
    "Connecting to node...",
    "Decrypting payload...",
    "Rootkit installed successfully.",
    "Scanning local subnet for vulnerabilities...",
    "Port 22 open. Initiating brute force...",
    "Firewall ping sweep: 45 nodes responding.",
    "Injecting shellcode...",
    "Access denied. Retrying...",
    "Kernel panic avoided.",
    "Dumping physical memory...",
    "Analyzing packet capture...",
    "Syslog cleared.",
    "Overriding safety protocols...",
    "Handshake complete.",
    "Compiling exploit payload...",
    "WARNING: Trace detected. Rerouting...",
    "Connection established on port 8080.",
    "Spawning daemon process...",
    "Executing sudo payload...",
    "Uploading data shard...",
    "Signal lost. Reacquiring...",
    "Parsing subnet mask...",
    "Ping: 12ms. Packet loss: 0%.",
    "Allocating virtual memory swap...",
    "Subroutine execution time: 14ms.",
    "Bypassing mainframe security grids...",
    "Tracing origin IP address...",
]

def get_random_log():
    return random.choice(LINES)
