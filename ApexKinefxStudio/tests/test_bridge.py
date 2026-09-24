import json
import os
import socket
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestBridge(unittest.TestCase):
    """The Houdini bridge protocol, running against fake_hou in a subprocess."""

    @classmethod
    def setUpClass(cls):
        cls.port = _free_port()
        cls.proc = subprocess.Popen([sys.executable, os.path.join(HERE, "run_fake_bridge.py"), str(cls.port)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", cls.port), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("bridge did not start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=10)

    def call(self, method, params=None):
        with socket.create_connection(("127.0.0.1", self.port), timeout=30) as s:
            s.sendall((json.dumps({"id": 1, "method": method, "params": params or {}}) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
        return json.loads(buf)

    def test_ping(self):
        r = self.call("ping")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["result"]["houdini"], "22.0.0")

    def test_selftest_and_clean(self):
        r = self.call("selftest", {"cases": ["car", "insect"]})
        self.assertTrue(r["ok"], r)
        self.assertEqual(sorted(r["result"]["passed"]), ["car", "insect"])
        self.assertTrue(self.call("clean")["ok"])

    def test_build_and_node_info(self):
        r = self.call("build", {"tool": "vehicle", "kwargs": {"vehicle_type": "tank", "name": "t"}})
        self.assertTrue(r["ok"], r)
        info = self.call("node_info", {"path": "/obj/t/drive"})["result"]
        self.assertTrue("kinematic vehicle driver" in info["snippet"], "drive snippet missing")

    def test_errors_are_reported_not_raised(self):
        r = self.call("build", {"tool": "nope"})
        self.assertFalse(r["ok"])
        self.assertIn("unknown tool", r["error"])
        self.assertFalse(self.call("no_such_method")["ok"])
        r = self.call("run_python", {"code": "raise ValueError('boom')"})
        self.assertFalse(r["ok"])
        self.assertIn("boom", r["error"])

    def test_run_python_and_reload(self):
        r = self.call("run_python", {"code": "print('hi'); result = 1 + 2"})
        self.assertEqual(r["result"], {"stdout": "hi\n", "result": 3})
        self.assertTrue(self.call("reload")["ok"])


if __name__ == "__main__":
    unittest.main()
