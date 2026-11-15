#!/usr/bin/env python3
"""Acquire at most three small official map API sections, then merge offline.

Network requires --acquire. No redirects/retries; 10 MB/response, 30 MB/operation.
All attempts (including failures) are recorded separately from earlier evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

from route_osm import ROOT, RAW, NoRedirect, read_bounded, utc_now, merge_sources

BBOXES = ((16.17, 48.26, 16.21, 48.29),
          (16.20, 48.245, 16.25, 48.27),
          (16.24, 48.235, 16.28, 48.255))
TOTAL_LIMIT = 30_000_000
RESPONSE_LIMIT = 10_000_000


def acquire_sections(raw_dir=RAW, bboxes=BBOXES):
    if not 1 <= len(bboxes) <= 3:
        raise ValueError("Only one to three requests allowed")
    raw_dir.mkdir(parents=True, exist_ok=True)
    budget = [TOTAL_LIMIT]
    attempts = []
    opener = urllib.request.build_opener(NoRedirect)
    stamp = utc_now().replace(":", "").replace(".", "")
    log_path = raw_dir / f"sections_{stamp}.json"
    for bbox in bboxes:
        url = "https://api.openstreetmap.org/api/0.6/map?bbox=" + ",".join(map(str, bbox))
        attempt = {"url": url, "requested_at_utc": utc_now(), "success": False}
        attempts.append(attempt)
        before = budget[0]
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "Assetto-Exelberg-M1/1.0 (private route research; Python stdlib)",
                "Accept": "application/xml", "Accept-Encoding": "identity"})
            deadline = time.monotonic() + 25
            try:
                response = opener.open(request, timeout=25)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                attempt["http_status"] = response.code
                # Error bodies are intentionally limited to 8 KiB, including HTTP 400.
                payload = read_bounded(response, budget, deadline,
                                       limit=RESPONSE_LIMIT if response.code == 200 else 8192)
                if response.code != 200:
                    attempt["error_body"] = payload.decode("utf-8", errors="replace")
                    raise ValueError(f"HTTP {response.code}")
                if response.headers.get("Content-Encoding", "identity") != "identity":
                    raise ValueError("Unexpected content encoding")
            digest = hashlib.sha256(payload).hexdigest()
            filename = f"map_{digest[:16]}.osm"
            destination = raw_dir / filename
            if destination.exists() and destination.read_bytes() != payload:
                raise ValueError("Source checksum filename collision")
            if not destination.exists():
                destination.write_bytes(payload)
            provenance = {"source_file": filename, "sha256": digest, "url": url,
                          "requested_at_utc": attempt["requested_at_utc"], "received_at_utc": utc_now(),
                          "received_bytes": len(payload), "license": "ODbL-1.0",
                          "attribution": "© OpenStreetMap contributors",
                          "license_url": "https://www.openstreetmap.org/copyright"}
            manifest = raw_dir / f"provenance_{digest[:16]}.json"
            if not manifest.exists():
                manifest.write_text(json.dumps(provenance, indent=2) + "\n")
            attempt.update(success=True, source_file=filename, sha256=digest)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            attempt["error"] = str(exc)
        finally:
            attempt["received_bytes"] = before - budget[0]
            attempt["finished_at_utc"] = utc_now()
            log_path.write_text(json.dumps({"attempts": attempts,
                "total_received_bytes": TOTAL_LIMIT - budget[0],
                "limits": {"requests": 3, "response_bytes": RESPONSE_LIMIT,
                           "total_bytes": TOTAL_LIMIT, "timeout_seconds": 25},
                "retries": 0}, indent=2) + "\n")
    return log_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquire", action="store_true")
    args = parser.parse_args()
    if args.acquire:
        print(acquire_sections())
    sources = sorted(RAW.glob("map_*.osm"))
    if not sources:
        parser.error("No preserved XML sources")
    output = ROOT / "data/interim/osm/merged.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    document = merge_sources(sources)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    print(f"Merged {len(sources)} sources, {len(document['elements'])} elements: {output}")


if __name__ == "__main__":
    main()
