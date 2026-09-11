import os
import shutil
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "tests", "nano_fx_math.cpp")


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ not available")
def test_nano_effect_math_stays_on_screen(tmp_path):
    """Compile and run the host harness that mirrors the Nano effect math.

    It proves the fixed NEURAL_MESH / OPTICS_CAMO / RAM_ALLOCATOR effects keep
    every drawn coordinate inside the 128x64 OLED canvas, and that the original
    NEURAL_MESH really did overflow a 16-bit int and draw off-screen.
    """
    binary = str(tmp_path / "nano_fx_math")
    comp = subprocess.run(["g++", "-O1", "-std=c++11", SRC, "-o", binary],
                          capture_output=True, text=True)
    assert comp.returncode == 0, f"compile failed:\n{comp.stderr}"

    run = subprocess.run([binary], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, f"nano fx math check failed:\n{run.stdout}\n{run.stderr}"
    assert "ALL NANO FX MATH OK" in run.stdout
