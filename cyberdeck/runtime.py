"""
Shared runtime references for cross-module access.

The UI screens need to reach the live FSM and display surface, but importing
them from ``main`` with ``from ..main import fsm`` is fragile: when the app is
launched as ``python -m cyberdeck.main`` the module is loaded as ``__main__``
and those imports bind to a *second* copy of ``main`` whose ``fsm`` is still
``None`` (the classic double-import bug). That silently broke boot
auto-advance on the suit.

This module is imported normally (never run as ``__main__``), so there is
exactly one instance of it. ``main`` publishes the live objects here and the
UI reads them via attribute access at call time, which always sees the current
value regardless of how the app was launched.
"""

# Set by main.main() once the FSM and display are up.
fsm = None
screen = None
