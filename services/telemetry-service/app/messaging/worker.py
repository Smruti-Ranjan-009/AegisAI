from __future__ import annotations

import logging
import signal
import sys
import threading

from .config import KafkaSettings
from .consumer import TelemetryWorker


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stopping = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stopping.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    worker = TelemetryWorker(KafkaSettings.from_environment())
    worker.run(stopping.is_set)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        logging.exception("telemetry worker stopped with an error")
        sys.exit(2)
