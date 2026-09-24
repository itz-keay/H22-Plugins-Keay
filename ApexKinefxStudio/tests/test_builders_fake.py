import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class TestBuildersWithFakeHou(unittest.TestCase):
    """Runs every network builder against a recording fake of ``hou``."""

    def test_all_builders(self):
        proc = subprocess.run([sys.executable, os.path.join(HERE, "run_fake_builders.py")],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
