import argparse
import json
import signal
import time
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--fake-thread", default="fake-thread")
parser.add_argument("--sleep", type=float, default=0)
parser.add_argument("--marker")
parser.add_argument("--exit-code", type=int, default=0)
parser.add_argument("prompt", nargs="?")
args = parser.parse_args()


def mark_interrupt(*_args):
    if args.marker:
        Path(args.marker).write_text("interrupted", encoding="utf-8")
    raise SystemExit(130)


signal.signal(signal.SIGTERM, mark_interrupt)
if hasattr(signal, "SIGBREAK"):
    signal.signal(signal.SIGBREAK, mark_interrupt)

print(json.dumps({"type": "thread.started", "thread_id": args.fake_thread}, ensure_ascii=False), flush=True)
if args.sleep:
    time.sleep(args.sleep)
print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": args.prompt or "OK"}}, ensure_ascii=False), flush=True)
print(json.dumps({"type": "turn.completed", "usage": {"output_tokens": 1}}, ensure_ascii=False), flush=True)
raise SystemExit(args.exit_code)
