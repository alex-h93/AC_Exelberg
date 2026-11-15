#!/usr/bin/env python3
"""Bounded, stdlib-only TIFF metadata inspection; never requests pixel blocks.

Run once per acquisition operation. Defaults are the two registered BEV URLs.
No redirects, retries, HEAD requests, or external offset/count-table downloads.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import struct
import urllib.error
import urllib.request

URLS = {
    "dtm": "https://data.bev.gv.at/download/ALS/DTM/20250915/ALS_DTM_CRS3035RES50000mN2800000E4750000.tif",
    "orthophoto": "https://data.bev.gv.at/download/DOP/20250415/2024460_Mosaik_RGB.tif",
}
CAP = 2_000_000
MAX_RANGE = 65_536
MAX_REQUESTS = 4
# TIFF types, including BigTIFF LONG8/SLONG8/IFD8.
TYPES = {1: (1, "B"), 2: (1, None), 3: (2, "H"), 4: (4, "I"),
         5: (8, None), 6: (1, "b"), 7: (1, None), 8: (2, "h"),
         9: (4, "i"), 10: (8, None), 11: (4, "f"), 12: (8, "d"),
         13: (4, "I"), 16: (8, "Q"), 17: (8, "q"), 18: (8, "Q")}
NAMES = {256: "width", 257: "height", 258: "bits_per_sample", 259: "compression",
         262: "photometric", 273: "strip_offsets", 277: "samples_per_pixel",
         278: "rows_per_strip", 279: "strip_byte_counts", 284: "planar_configuration",
         322: "tile_width", 323: "tile_height", 324: "tile_offsets",
         325: "tile_byte_counts", 330: "sub_ifds", 339: "sample_format",
         33550: "model_pixel_scale", 33922: "model_tiepoint", 34264: "model_transformation",
         34735: "geo_key_directory", 34736: "geo_double_params", 34737: "geo_ascii_params"}
TABLES = {273, 279, 324, 325}


class ProbeError(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_range(status, headers, start, size, total=None):
    if status != 206:
        raise ProbeError(f"expected HTTP 206, got {status}; body not read")
    if headers.get("Content-Encoding") is not None:
        raise ProbeError("Content-Encoding present; body not read")
    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", headers.get("Content-Range", ""))
    if not match:
        raise ProbeError("missing/malformed Content-Range; body not read")
    first, last, length = map(int, match.groups())
    if (first, last) != (start, start + size - 1) or last >= length:
        raise ProbeError("incorrect Content-Range; body not read")
    if total is not None and total != length:
        raise ProbeError("object length changed; body not read")
    content_length = headers.get("Content-Length")
    if content_length is not None and content_length != str(size):
        raise ProbeError("incorrect Content-Length; body not read")
    return length


class Budget:
    def __init__(self):
        self.actual_bytes = 0
        self.failed = False


class Remote:
    def __init__(self, url, budget):
        self.url, self.budget = url, budget
        self.requests = 0
        self.total = None
        self.chunks = []
        self.cache = []
        self.opener = urllib.request.build_opener(NoRedirect())

    def read(self, offset, size):
        if offset < 0 or not 0 < size <= MAX_RANGE:
            raise ProbeError("invalid or oversized metadata range")
        if self.total is not None and offset + size > self.total:
            raise ProbeError("metadata offset outside object")
        for start, data in self.cache:
            if start <= offset and offset + size <= start + len(data):
                return data[offset - start:offset - start + size]
        if self.budget.failed:
            raise ProbeError("network stopped after earlier failure")
        if self.requests >= MAX_REQUESTS or self.budget.actual_bytes + size > CAP:
            raise ProbeError("metadata request/byte budget exhausted")
        self.requests += 1
        record = {"offset": offset, "requested_bytes": size, "actual_bytes": 0}
        self.chunks.append(record)
        data = bytearray()
        response = None
        try:
            req = urllib.request.Request(self.url, headers={
                "Range": f"bytes={offset}-{offset + size - 1}",
                "Accept-Encoding": "identity",
                "User-Agent": "Assetto-Exelberg-MetadataProbe/1.0 (bounded TIFF metadata research)",
            })
            response = self.opener.open(req, timeout=20)
            record["status"] = response.status
            record["headers"] = dict(response.headers.items())
            self.total = validate_range(response.status, response.headers, offset, size, self.total)
            while len(data) < size:
                block = response.read(min(8192, size - len(data)))
                if not block:
                    break
                data.extend(block)
                self.budget.actual_bytes += len(block)
            if len(data) != size:
                raise ProbeError("short metadata response")
        except Exception as exc:
            self.budget.failed = True
            record["error"] = str(exc)
            # HTTPError is also a response: close it without reading its body.
            if isinstance(exc, urllib.error.HTTPError):
                exc.close()
            raise ProbeError(str(exc)) from exc
        finally:
            if response is not None:
                response.close()
            record["actual_bytes"] = len(data)
            record["sha256"] = hashlib.sha256(data).hexdigest()
        self.cache.append((offset, bytes(data)))
        return bytes(data)


def header(data):
    if len(data) < 8 or data[:2] not in (b"II", b"MM"):
        raise ProbeError("invalid TIFF header")
    endian = "<" if data[:2] == b"II" else ">"
    version = struct.unpack_from(endian + "H", data, 2)[0]
    if version == 42:
        return endian, False, struct.unpack_from(endian + "I", data, 4)[0]
    if version == 43 and len(data) >= 16:
        if struct.unpack_from(endian + "HH", data, 4) != (8, 0):
            raise ProbeError("unsupported BigTIFF offset size/reserved field")
        return endian, True, struct.unpack_from(endian + "Q", data, 8)[0]
    raise ProbeError("unsupported/truncated TIFF header")


def values(raw, type_id, count, endian):
    width, fmt = TYPES[type_id]
    if len(raw) != width * count:
        raise ProbeError("truncated tag value")
    if fmt:
        return list(struct.unpack(endian + str(count) + fmt, raw))
    if type_id == 2:
        return raw.rstrip(b"\0").decode("ascii", errors="replace")
    return raw.hex()


def directory(raw, count, endian, big):
    entry_size, inline_size = (20, 8) if big else (12, 4)
    if len(raw) != count * entry_size + inline_size:
        raise ProbeError("truncated IFD")
    tags = {}
    for index in range(count):
        pos = index * entry_size
        tag, type_id, number = struct.unpack_from(endian + ("HHQ" if big else "HHI"), raw, pos)
        if tag in tags:
            raise ProbeError("duplicate IFD tag")
        slot = raw[pos + entry_size - inline_size:pos + entry_size]
        item = {"type": type_id, "count": number}
        if type_id in TYPES:
            size = TYPES[type_id][0] * number
            item["bytes"] = size
            if size <= inline_size:
                item["values"] = values(slot[:size], type_id, number, endian)
            else:
                item["offset"] = struct.unpack(endian + ("Q" if big else "I"), slot)[0]
        tags[tag] = item
    next_ifd = struct.unpack_from(endian + ("Q" if big else "I"), raw, count * entry_size)[0]
    return tags, next_ifd


def inspect(remote):
    endian, big, first = header(remote.read(0, 16))
    result = {"byte_order": "little" if endian == "<" else "big", "format": "BigTIFF" if big else "TIFF",
              "first_ifd_offset": first, "cog_status": "not validated (range support alone is insufficient)",
              "pixel_validity_and_road_coverage": "not tested", "transfer_prediction_bytes": None}
    if first < (16 if big else 8):
        raise ProbeError("invalid first IFD offset")
    count_size, entry_size = (8, 20) if big else (2, 12)
    count = struct.unpack(endian + ("Q" if big else "H"), remote.read(first, count_size))[0]
    size = count * entry_size + (8 if big else 4)
    if size > MAX_RANGE:
        raise ProbeError("IFD too large for bounded inspection")
    tags, next_ifd = directory(remote.read(first + count_size, size), count, endian, big)
    # At most one additional request remains. Prefer CRS keys over optional
    # sample arrays. Never retrieve external block offset/byte-count arrays.
    for tag in (34735, 33550, 33922, 34264, 34736, 34737, 258, 339, 330):
        item = tags.get(tag, {})
        if "offset" in item and 0 < item["bytes"] <= 4096 and remote.requests < MAX_REQUESTS:
            item["values"] = values(remote.read(item["offset"], item["bytes"]), item["type"], item["count"], endian)
    result["tags"] = {NAMES.get(tag, str(tag)): item for tag, item in tags.items()}
    result["next_ifd_offset"] = next_ifd
    result["overview_status"] = "IFD links reported only; overview directories not fetched within request budget"
    def scalar(tag, default=None):
        val = tags.get(tag, {}).get("values", [])
        return val[0] if isinstance(val, list) and val else default
    width, height = scalar(256), scalar(257)
    tiled = 324 in tags
    bw, bh = (scalar(322), scalar(323)) if tiled else (width, scalar(278, height))
    result["layout"] = {"organization": "tiles" if tiled else "strips", "block_width": bw, "block_height": bh}
    if width and height and bw and bh:
        planes = scalar(277, 1) if scalar(284, 1) == 2 else 1
        result["layout"]["expected_blocks"] = ((width + bw - 1) // bw) * ((height + bh - 1) // bh) * planes
    result["sample_defaults_if_absent"] = {"samples_per_pixel": 1, "bits_per_sample": 1, "sample_format": "unsigned integer", "compression": "none", "planar_configuration": "chunky"}
    result["sample_format_codes"] = {"1": "unsigned integer", "2": "signed integer", "3": "IEEE float", "4": "undefined"}
    result["window_read_assessment"] = (
        "Tiled layout likely supports selective windows; compressed sizes, table access and COG ordering unverified."
        if tiled else "Full-width strips; window reads require intersecting strips. Large strip heights may be expensive; compressed transfer unknown.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/raw/bev_metadata"))
    args = parser.parse_args()
    # Never overwrite earlier acquisition evidence.
    args.output.mkdir(parents=True, exist_ok=True)
    paths = {name: args.output / (name + ".json") for name in URLS}
    if any(path.exists() for path in paths.values()):
        parser.error("output exists; preserve it and choose a new --output directory")
    budget = Budget()
    for name, url in URLS.items():
        remote = Remote(url, budget)
        report = {"url": url, "retrieved_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  "limits": {"operation_bytes": CAP, "range_bytes": MAX_RANGE, "requests_per_raster": MAX_REQUESTS, "timeout_seconds": 20},
                  "license_reference": "docs/DATA_SOURCES.md; BEV CC BY 4.0 metadata; preserve attribution",
                  "source_range_advertisement": "Previously advertised; not a COG claim"}
        try:
            report["metadata"] = inspect(remote)
        except ProbeError as exc:
            budget.failed = True
            report["error"] = str(exc)
        report.update(requests=remote.requests, actual_bytes=sum(c["actual_bytes"] for c in remote.chunks),
                      object_bytes=remote.total, chunks=remote.chunks, cumulative_operation_bytes=budget.actual_bytes)
        paths[name].write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(f"{name}: {report['actual_bytes']} bytes, {remote.requests} requests; {report.get('error', 'metadata inspected')}")
    print(f"Total response body bytes read: {budget.actual_bytes}")


if __name__ == "__main__":
    main()
