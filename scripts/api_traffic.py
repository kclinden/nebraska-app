"""Generate bounded, read-only traffic against an owned Nebraska API deployment."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import itertools
import json
import math
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


ENDPOINTS = (
    ("/api/v1/games", list),
    ("/api/v1/players", list),
    ("/api/v1/players?q=Raiola", list),
    ("/openapi.json", dict),
)


def fetch(base, path, expected_type, timeout):
    started = time.monotonic()
    try:
        request = urllib.request.Request(base + path, headers={
            "Accept": "application/json", "User-Agent": "Nebraska-API-Traffic-Test/1.0",
        })
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
            status = str(response.status)
            if not isinstance(body, expected_type):
                status = "invalid-response"
    except urllib.error.HTTPError as error:
        status = str(error.code)
        error.close()
    except (OSError, ValueError, urllib.error.URLError):
        status = "request-error"
    return path, status, time.monotonic() - started


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Base URL of your owned deployment")
    parser.add_argument("--duration", type=int, default=30, help="Seconds to send traffic (1-300)")
    parser.add_argument("--rate", type=int, default=10, help="Total requests per second (1-50)")
    parser.add_argument("--workers", type=int, default=4, help="Maximum concurrent requests (1-16)")
    parser.add_argument("--timeout", type=int, default=10, help="Per-request timeout in seconds (1-30)")
    args = parser.parse_args()
    for name, maximum in (("duration", 300), ("rate", 50), ("workers", 16), ("timeout", 30)):
        if not 1 <= getattr(args, name) <= maximum:
            parser.error(f"--{name} must be between 1 and {maximum}")
    parsed = urllib.parse.urlsplit(args.url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        parser.error("--url must be an HTTP(S) origin without credentials, a path, query, or fragment")
    base = args.url.rstrip("/")
    lock = threading.Lock()
    pacing = threading.Event()
    endpoints = itertools.cycle(ENDPOINTS)
    started = time.monotonic()
    deadline = started + args.duration
    next_slot = started

    def worker():
        nonlocal next_slot
        results = []
        while True:
            with lock:
                slot = max(next_slot, time.monotonic())
                if slot >= deadline:
                    return results
                next_slot = slot + 1 / args.rate
                path, expected_type = next(endpoints)
            pacing.wait(max(0, slot - time.monotonic()))
            if time.monotonic() >= deadline:
                return results
            results.append(fetch(base, path, expected_type, args.timeout))

    print(f"Target: {base}", flush=True)
    print(f"GET only; {args.duration}s; <= {args.rate} requests/s; <= {args.workers} concurrent", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = [result for batch in pool.map(lambda unused: worker(), range(args.workers)) for result in batch]
    elapsed = time.monotonic() - started
    statuses = Counter(status for path, status, latency in results)
    latencies = sorted(latency * 1000 for path, status, latency in results)
    failures = sum(count for status, count in statuses.items() if status != "200")
    print(f"Completed: {len(results)} in {elapsed:.1f}s ({len(results) / elapsed:.1f} requests/s)")
    print(f"Successes: {len(results) - failures}; failures: {failures}; statuses: {dict(statuses)}")
    if latencies:
        percentile95 = latencies[math.ceil(len(latencies) * 0.95) - 1]
        print(f"Latency ms: median={statistics.median(latencies):.0f}, p95={percentile95:.0f}, max={max(latencies):.0f}")
    for path, expected_type in ENDPOINTS:
        counts = Counter(status for result_path, status, latency in results if result_path == path)
        print(f"  {path}: {dict(counts)}")
    return 1 if failures or not results else 0


if __name__ == "__main__":
    raise SystemExit(main())