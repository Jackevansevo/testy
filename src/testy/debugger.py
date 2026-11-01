"""--pdb: debuggers that use the real terminal while tests' own I/O stays discarded.

Only imported with --pdb, which also runs one file at a time, so swapping the
sys streams around a debugger session can't affect another thread.
"""

import pdb  # noqa: T100 - debugging is what --pdb is for
import sys
from typing import TextIO


class TerminalPdb(pdb.Pdb):
    def __init__(self, stdin: TextIO, stdout: TextIO, **kwargs):
        # Like Python's own breakpoint(); pdb still checks the terminal and NO_COLOR.
        super().__init__(stdin=stdin, stdout=stdout, colorize=True, **kwargs)
        # Passing stdout turns off input() (and so readline editing and history);
        # the swap in interaction() makes input() use the terminal, so turn it back on.
        self.use_rawinput = True

    def interaction(self, *args, **kwargs):
        saved = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = self.stdin, self.stdout
        try:
            super().interaction(*args, **kwargs)
        finally:
            sys.stdin, sys.stdout = saved


def breakpoint_hook(stdin: TextIO, stdout: TextIO):
    """A `sys.breakpointhook` that stops in the caller with a TerminalPdb."""

    def hook(*args, **kwargs):
        TerminalPdb(stdin, stdout).set_trace(sys._getframe(1))

    return hook


def post_mortem(e: Exception, stdin: TextIO, stdout: TextIO) -> bool:
    """Debug the failure `e` where it happened. Returns True if the user quit."""
    debugger = TerminalPdb(stdin, stdout)
    debugger.reset()
    debugger.interaction(None, e.__traceback__)
    return debugger.quitting
