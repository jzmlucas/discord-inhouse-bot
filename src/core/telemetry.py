import threading
from collections import defaultdict
from time import perf_counter


def _metric_key(name: str, labels: dict | None):
    if not labels:
        return name
    parts = [f"{k}={labels[k]}" for k in sorted(labels)]
    return f"{name}|{'|'.join(parts)}"


class Telemetry:
    def __init__(self):
        self._lock = threading.Lock()
        self._counters = defaultdict(int)
        self._timers = defaultdict(list)

    def inc(self, name: str, value: int = 1, **labels):
        key = _metric_key(name, labels)
        with self._lock:
            self._counters[key] += value

    def observe(self, name: str, value: float, **labels):
        key = _metric_key(name, labels)
        with self._lock:
            self._timers[key].append(float(value))

    def now(self):
        return perf_counter()

    def observe_since(self, name: str, started_at: float, **labels):
        self.observe(name, perf_counter() - started_at, **labels)

    def snapshot(self):
        with self._lock:
            counters = dict(self._counters)
            timers = {}
            for key, values in self._timers.items():
                if not values:
                    continue
                count = len(values)
                total = sum(values)
                timers[key] = {
                    "count": count,
                    "avg": total / count,
                    "max": max(values),
                }
            return {"counters": counters, "timers": timers}
