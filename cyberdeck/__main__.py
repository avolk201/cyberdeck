"""Allow ``python3 -m cyberdeck`` to launch the deck OS directly.

For the crash-resilient supervised entry point used on the suit, run
``python3 run.py`` instead (it respawns the app on crash or hang).
"""
from cyberdeck.main import main

if __name__ == "__main__":
    main()
