import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
import sys as python_sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from luna_agent_bridge.codex_adapter import CodexInvocation
from luna_agent_bridge.process_control import ProcessController
from luna_agent_bridge.scheduler import Scheduler, SchedulerBusyError


class ProcessSchedulerTests(unittest.TestCase):
    def test_fifth_job_waits_until_a_slot_is_free(self):
        scheduler = Scheduler(max_workers=4)
        gates = [threading.Event() for _ in range(5)]
        futures = []
        for index in range(5):
            futures.append(scheduler.submit(str(index), lambda i=index: gates[i].wait(5)))
        deadline = time.monotonic() + 2
        while scheduler.running_count() != 4 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(4, scheduler.running_count())
        self.assertEqual(1, scheduler.queued_count())
        gates[0].set()
        deadline = time.monotonic() + 2
        while scheduler.running_count() != 4 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(4, scheduler.running_count())
        for gate in gates:
            gate.set()
        for future in futures:
            future.result(timeout=2)
        scheduler.shutdown()

    def test_same_agent_cannot_run_two_tasks_at_once(self):
        scheduler = Scheduler(max_workers=4)
        gate = threading.Event()
        scheduler.submit("same", lambda: gate.wait(2))
        with self.assertRaises(SchedulerBusyError):
            scheduler.submit("same", lambda: None)
        gate.set()
        scheduler.shutdown(wait=True)

    def test_interrupt_terminates_only_the_owned_process(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "interrupt.marker"
            fake = Path(__file__).parent / "fake_codex.py"
            invocation = CodexInvocation(
                argv=(python_sys.executable, str(fake), "--fake-thread", "interrupt-thread", "--sleep", "30", "--marker", str(marker), "等待"),
                cwd=Path(directory),
            )
            running = ProcessController().start(invocation)
            time.sleep(0.2)
            running.interrupt(grace_seconds=1)
            self.assertIsNotNone(running.poll())


if __name__ == "__main__":
    unittest.main()
