#!/usr/bin/env python3
"""
Cyberdeck OS Launcher (Supervised)

This is the crash-resilient entry point. It runs the app under a supervisor
that respawns it on crash or hang, keeping the X session alive across
restarts. For a single unsupervised run (e.g. debugging), invoke the app
directly with:  python3 -m cyberdeck.main
"""
import sys

from cyberdeck.supervisor import run_forever

if __name__ == "__main__":
    sys.exit(run_forever())
