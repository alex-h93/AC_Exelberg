#!/usr/bin/env python3
"""Bounded OSM acquisition and provisional, directed route reconstruction (stdlib).

Run --acquire to request source data (at most three requests); run without it to
rebuild from the saved source. No terrain/elevation or screenshot matching occurs.
"""
import argparse
import datetime as dt
from dataclasses import dataclass
import hashlib
import heapq
import html
import itertools
import json
import math
from pathlib import Path
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/osm"
RESPONSE_LIMIT = 10_000_000
TOTAL_LIMIT = 50_000_000
ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
QUERY = '''[out:json][timeout:25][maxsize:10000000];
way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link|unclassified|residential|living_street|service|road)$"](48.235,16.145,48.310,16.280);
(._;>;);
out body;
'''


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_bounded(response, budget, deadline, limit=RESPONSE_LIMIT):
    """Count body bytes, including unsuccessful bodies; never read past caps.

    Each socket operation has a 20 s timeout in acquire(); the 60 s deadline is
    checked between single reads (at most one socket timeout of overrun).
    """
    chunks = []
    count = 0
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError("Response wall-clock deadline exceeded")
        remaining = min(limit - count, budget[0])
        if remaining <= 0:
            raise ValueError("Response or total transfer cap reached (body rejected)")
        # HTTPResponse.read1 performs at most one underlying read, so a peer
        # trickling bytes cannot keep a large read alive indefinitely.
        block = response.read1(min(65536, remaining))
        budget[0] -= len(block)
        count += len(block)
        if not block:
            return b"".join(chunks)
        chunks.append(block)


def acquire(raw_dir=RAW):
    raw_dir.mkdir(parents=True, exist_ok=True)
    budget = [TOTAL_LIMIT]
    attempts = []
    opener = urllib.request.build_opener(NoRedirect)
    for endpoint in ENDPOINTS:
        attempt = {"endpoint": endpoint, "requested_at_utc": utc_now()}
        attempts.append(attempt)
        before = budget[0]
        try:
            request = urllib.request.Request(
                endpoint, data=urllib.parse.urlencode({"data": QUERY}).encode(),
                headers={"User-Agent": "Assetto-Exelberg-M1/1.0 (private route research; Python stdlib)",
                         "Accept": "application/json", "Accept-Encoding": "identity"})
            deadline = time.monotonic() + 60
            try:
                response = opener.open(request, timeout=20)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                payload = read_bounded(response, budget, deadline)
                attempt["http_status"] = response.code
                if response.code != 200:
                    raise ValueError(f"HTTP {response.code}")
                if response.headers.get("Content-Encoding", "identity") != "identity":
                    raise ValueError("Unexpected content encoding")
            document = json.loads(payload)
            if document.get("remark") or not document.get("elements"):
                raise ValueError("Overpass remark or empty elements: " + str(document.get("remark")))
            digest = hashlib.sha256(payload).hexdigest()
            filename = "roads_" + digest[:16] + ".json"
            destination = raw_dir / filename
            if destination.exists() and destination.read_bytes() != payload:
                raise ValueError("Existing source collision")
            if not destination.exists():
                destination.write_bytes(payload)
            attempt["success"] = True
            metadata = {"source_file": filename, "sha256": digest, "query": QUERY,
                        "bbox_south_west_north_east": [48.235, 16.145, 48.310, 16.280],
                        "license": "ODbL-1.0", "attribution": "© OpenStreetMap contributors",
                        "license_url": "https://www.openstreetmap.org/copyright",
                        "overpass_timestamp_osm_base": document.get("osm3s", {}).get("timestamp_osm_base"),
                        "status": "source acquired; route not yet verified"}
        except (OSError, ValueError, urllib.error.URLError, socket.timeout) as exc:
            attempt["error"] = str(exc)
            attempt["success"] = False
        attempt["received_bytes"] = before - budget[0]
        attempt["finished_at_utc"] = utc_now()
        if attempt["success"]:
            metadata.update(attempts=attempts, total_received_bytes=TOTAL_LIMIT - budget[0])
            manifest = raw_dir / ("provenance_" + digest[:16] + ".json")
            if not manifest.exists():
                manifest.write_text(json.dumps(metadata, indent=2) + "\n")
            return destination, manifest
    failure = {"query": QUERY, "attempts": attempts,
               "total_received_bytes": TOTAL_LIMIT - budget[0], "status": "acquisition blocked"}
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    (raw_dir / f"failed_{stamp}.json").write_text(json.dumps(failure, indent=2) + "\n")
    raise RuntimeError("All three bounded endpoint attempts failed: " + str(attempts))


START = (16.1591442, 48.3012763)  # WGS84 longitude, latitude
FINISH = (16.2702098, 48.2439815)
EARTH_RADIUS_M = 6_371_008.8
DRIVABLE = {"motorway", "motorway_link", "trunk", "trunk_link", "primary",
            "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link",
            "unclassified", "residential", "living_street", "service", "road"}


def distance(a, b):
    """Spherical great-circle distance, metres; coordinates are (lon, lat)."""
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2)**2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, h)))


def project_to_edge(point, a, b):
    """Local equirectangular segment projection; return lon/lat, fraction, offset.

    Appropriate for short OSM edges at this latitude, not a geodesic survey.
    Clamps to segment ends rather than selecting an arbitrary nearest vertex.
    """
    scale = math.cos(math.radians((a[1] + b[1] + point[1]) / 3))
    dx, dy = (b[0] - a[0]) * scale, b[1] - a[1]
    px, py = (point[0] - a[0]) * scale, point[1] - a[1]
    denominator = dx * dx + dy * dy
    t = max(0.0, min(1.0, (px * dx + py * dy) / denominator)) if denominator else 0.0
    snapped = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
    return snapped, t, distance(point, snapped)


def corridor_way(tags):
    refs = {value.strip().replace(" ", "").upper() for value in tags.get("ref", "").split(";")}
    name = tags.get("name", "").casefold().replace("ß", "ss")
    return "L120" in refs or name in {"neuwaldegger strasse", "tullner strasse", "exelbergstrasse"}


def car_access(tags):
    if tags.get("highway") not in DRIVABLE or tags.get("area") == "yes":
        return False
    # Most-specific motorcar rule overrides generic access restrictions.
    access = next((tags[k] for k in ("motorcar", "motor_vehicle", "vehicle", "access") if k in tags), "yes")
    return access in {"yes", "permissive", "designated", "official"}


def directions(tags):
    """Legal base directions for cars. Conditional/directional access needs review."""
    value = next((tags[k] for k in ("oneway:motorcar", "oneway:motor_vehicle", "oneway") if k in tags), None)
    if value in {"-1", "reverse"}:
        return (False, True)
    if value in {"yes", "1", "true"}:
        return (True, False)
    if value in {"no", "0", "false"}:
        return (True, True)
    if value is not None:  # e.g. reversible: not safely routable without schedule
        return (False, False)
    return (True, False) if tags.get("junction") == "roundabout" or tags.get("highway") == "motorway" else (True, True)


@dataclass
class Segment:
    key: tuple
    u: object
    v: object
    a: tuple
    b: tuple
    tags: dict
    forward: bool
    reverse: bool


@dataclass
class Edge:
    target: object
    a: tuple
    b: tuple
    way_id: int
    tags: dict

    @property
    def length(self):
        return distance(self.a, self.b)


def load_osm(source):
    """Read preserved map API XML or Overpass/derived JSON without modifying it."""
    payload = source.read_bytes()
    if source.suffix.lower() != ".osm":
        return json.loads(payload)
    root = ET.fromstring(payload)
    if root.tag != "osm":
        raise ValueError("Expected OSM XML root")
    elements = []
    for item in root:
        if item.tag not in {"node", "way", "relation"}:
            continue
        element = {"type": item.tag, "id": int(item.attrib["id"]),
                   "tags": {t.attrib["k"]: t.attrib["v"] for t in item.findall("tag")}}
        if "version" in item.attrib:
            element["version"] = int(item.attrib["version"])
        if item.tag == "node":
            element.update(lon=float(item.attrib["lon"]), lat=float(item.attrib["lat"]))
        elif item.tag == "way":
            element["nodes"] = [int(n.attrib["ref"]) for n in item.findall("nd")]
        else:
            element["members"] = [{"type": m.attrib["type"], "ref": int(m.attrib["ref"]),
                                   "role": m.attrib.get("role", "")} for m in item.findall("member")]
        elements.append(element)
    return {"elements": elements}


def merge_sources(sources):
    """Deduplicate identities; prefer newer versions, reject same-version conflicts."""
    merged = {}
    originals = []
    for source in sources:
        document = load_osm(source)
        if document.get("remark"):
            raise ValueError("Incomplete source")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        original = {"source_file": str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source),
                    "sha256": digest, "license": "ODbL-1.0"}
        manifest = source.parent / f"provenance_{digest[:16]}.json"
        if manifest.exists():
            provenance = json.loads(manifest.read_text())
            if provenance.get("sha256") != digest:
                raise ValueError(f"Provenance checksum mismatch: {source}")
            original["provenance"] = provenance
        originals.append(original)
        for element in document["elements"]:
            key = (element["type"], element["id"])
            old = merged.get(key)
            if old is not None:
                if old.get("version", 0) == element.get("version", 0) and old != element:
                    raise ValueError(f"Conflicting same-version OSM element {key}")
                if old.get("version", 0) >= element.get("version", 0):
                    continue
            merged[key] = element
    return {"elements": [merged[k] for k in sorted(merged)], "sources": originals,
            "license": "ODbL-1.0", "attribution": "© OpenStreetMap contributors",
            "status": "derived merged OSM; originals preserved"}


def segments_from_osm(document, corridor_only=True):
    if document.get("remark"):
        raise ValueError("Incomplete Overpass response: " + str(document["remark"]))
    nodes = {e["id"]: (e["lon"], e["lat"]) for e in document["elements"] if e["type"] == "node"}
    segments = []
    for way in document["elements"]:
        if way["type"] != "way":
            continue
        tags = way.get("tags", {})
        if not car_access(tags) or (corridor_only and not corridor_way(tags)):
            continue
        forward, reverse = directions(tags)
        if not (forward or reverse):
            continue
        ids = way.get("nodes", [])
        for index, (u, v) in enumerate(zip(ids, ids[1:])):
            if u not in nodes or v not in nodes:
                raise ValueError(f"Missing geometry on way {way['id']}")
            if distance(nodes[u], nodes[v]) > 0:
                segments.append(Segment((way["id"], index), u, v, nodes[u], nodes[v], tags, forward, reverse))
    if not segments:
        raise ValueError("No eligible named-corridor car segments")
    return segments


def snap_endpoints(segments, start=START, finish=FINISH, max_offset=100):
    """Split each directed edge at endpoint projections, including same-edge snaps.

    Shared OSM node IDs define connectivity, never mere geometric crossings.
    """
    splits = {}
    snaps = []
    keys = []
    for label, point in (("start", start), ("finish", finish)):
        choices = [(project_to_edge(point, s.a, s.b), s) for s in segments]
        (coordinate, fraction, offset), segment = min(choices, key=lambda c: (c[0][2], c[1].key))
        if offset > max_offset:
            raise ValueError(f"{label} edge snap {offset:.1f} m exceeds {max_offset} m")
        if fraction <= 1e-12:
            key = segment.u
        elif fraction >= 1 - 1e-12:
            key = segment.v
        else:
            # Same projected position on the same edge must be one graph node.
            key = ("snap", segment.key, round(fraction, 12))
            splits.setdefault(segment.key, {})[key] = (fraction, coordinate)
        keys.append(key)
        snaps.append({"label": label, "requested_lon_lat": point, "snapped_lon_lat": coordinate,
                      "offset_m": offset, "way_id": segment.key[0], "edge_index": segment.key[1],
                      "fraction": fraction})
    graph = {}
    for segment in segments:
        chain = [(0.0, segment.u, segment.a), (1.0, segment.v, segment.b)]
        chain.extend((fraction, key, coordinate) for key, (fraction, coordinate) in splits.get(segment.key, {}).items())
        chain.sort(key=lambda item: item[0])
        for (_, u, a), (_, v, b) in zip(chain, chain[1:]):
            if segment.forward:
                graph.setdefault(u, []).append(Edge(v, a, b, segment.key[0], segment.tags))
            if segment.reverse:
                graph.setdefault(v, []).append(Edge(u, b, a, segment.key[0], segment.tags))
    return graph, keys[0], keys[1], snaps


def shortest_path(graph, start, finish):
    serial = itertools.count()
    queue = [(0.0, next(serial), start)]
    best = {start: 0.0}
    previous = {}
    while queue:
        cost, _, node = heapq.heappop(queue)
        if cost != best[node]:
            continue
        if node == finish:
            path = []
            while node != start:
                origin, edge = previous[node]
                path.append(edge)
                node = origin
            return list(reversed(path))
        for edge in graph.get(node, []):
            candidate = cost + edge.length
            if candidate < best.get(edge.target, math.inf):
                best[edge.target] = candidate
                previous[edge.target] = (node, edge)
                heapq.heappush(queue, (candidate, next(serial), edge.target))
    raise ValueError("No directed path on the allowed road corridor; do not substitute an arbitrary alternative")


def route_groups(path):
    groups = []
    for edge in path:
        name, ref = edge.tags.get("name", "(unnamed)"), edge.tags.get("ref", "")
        if not groups or (groups[-1]["name"], groups[-1]["ref"]) != (name, ref):
            groups.append({"name": name, "ref": ref, "length_m": 0.0, "way_ids": []})
        groups[-1]["length_m"] += edge.length
        if edge.way_id not in groups[-1]["way_ids"]:
            groups[-1]["way_ids"].append(edge.way_id)
    return groups


def svg_map(segments, coordinates):
    """Self-contained north-up schematic; approximate local metric aspect ratio."""
    all_points = [p for segment in segments for p in (segment.a, segment.b)] + coordinates
    west, east = min(p[0] for p in all_points), max(p[0] for p in all_points)
    south, north = min(p[1] for p in all_points), max(p[1] for p in all_points)
    aspect = math.cos(math.radians((south + north) / 2))
    scale = min(900 / max((east - west) * aspect, 1e-9), 650 / max(north - south, 1e-9))

    def xy(point):
        return 50 + (point[0] - west) * aspect * scale, 90 + (north - point[1]) * scale

    def points(items):
        return " ".join(f"{x:.2f},{y:.2f}" for x, y in map(xy, items))

    background = "".join(f'<polyline points="{points([s.a, s.b])}"/>' for s in segments)
    labels = []
    for label, point in (("Start: Königstetten", coordinates[0]), ("Finish: Marswiese", coordinates[-1])):
        x, y = xy(point)
        labels.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="black"/><text x="{x + 8:.2f}" y="{y - 8:.2f}">{html.escape(label)}</text>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="850" viewBox="0 0 1100 850">'
            '<rect width="1100" height="850" fill="white"/>'
            '<g font-family="sans-serif" font-size="16"><text x="30" y="30">PROVISIONAL OSM path — not screenshot-verified; north up</text>'
            f'<g stroke="#bbb" stroke-width="1" fill="none">{background}</g>'
            f'<polyline points="{points(coordinates)}" fill="none" stroke="#c22" stroke-width="3"/>'
            + "".join(labels) + '<text x="30" y="810">© OpenStreetMap contributors · ODbL · No sampled elevations</text></g></svg>\n')


def build(source):
    payload = source.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    document = load_osm(source)
    segments = segments_from_osm(document)
    graph, start, finish, snaps = snap_endpoints(segments)
    path = shortest_path(graph, start, finish)
    if not path:
        raise ValueError("Empty route")
    for first, second in zip(path, path[1:]):
        if first.b != second.a:
            raise ValueError("Discontinuous path")
    coordinates = [path[0].a] + [edge.b for edge in path]
    length = sum(edge.length for edge in path)
    groups = route_groups(path)
    warnings = ["Calculated provisional OSM path, NOT screenshot-verified final alignment.",
                "Road ref/name whitelist only (observed L120 and Exelbergstraße tags, no arbitrary fallback); Dopplerhütte and Scheiblingstein/Exelberg passage and junction/hairpin choices require coordinator screenshot review.",
                "Turn-restriction relations, conditional/directional access, barriers and lane-level restrictions are NOT enforced. No legal driving clearance is implied.",
                "No elevations sampled: coordinates are two-dimensional WGS84 longitude, latitude.",
                "Endpoint snapping uses local planar edge projection; lengths use a spherical Earth, not survey-grade measurements.",
                "Terrain/imagery valid-pixel coverage and acquisition dates remain unverified; M1 gate remains open."]
    if abs(length - 15200) > 1520:
        warnings.append("Length differs from screenshot's approximately 15.2 km by over 10%; investigate before acceptance.")
    flagged = sorted({edge.way_id for edge in path if any(":" in k or k in {"barrier", "restriction"} for k in edge.tags)})
    properties = {"status": "provisional_not_screenshot_verified", "direction": "Königstetten → Marswiese",
                  "length_m": length, "reference_length_m": 15200, "difference_m": length - 15200,
                  "source_sha256": digest, "source_file": str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source),
                  "attribution": "© OpenStreetMap contributors", "license": "ODbL-1.0",
                  "sources": document.get("sources", [{"source_file": str(source), "sha256": digest, "license": "ODbL-1.0"}]),
                  "bounds_west_south_east_north": [min(p[0] for p in coordinates), min(p[1] for p in coordinates),
                                                   max(p[0] for p in coordinates), max(p[1] for p in coordinates)],
                  "endpoint_snaps": snaps, "segments": groups, "warnings": warnings,
                  "ways_with_extra_tags_for_review": flagged}
    output = ROOT / "data/processed"
    output.mkdir(parents=True, exist_ok=True)
    geojson = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": properties,
               "geometry": {"type": "LineString", "coordinates": coordinates}}]}
    (output / "route.geojson").write_text(json.dumps(geojson, ensure_ascii=False, indent=2) + "\n")
    (output / "route.svg").write_text(svg_map(segments, coordinates))
    report = ["# Route report", "", "## Provisional calculation — not accepted final route", "",
              f"Source: `{properties['source_file']}`; SHA256 `{digest}`.",
              "License: ODbL-1.0; © OpenStreetMap contributors (https://www.openstreetmap.org/copyright).",
              f"Direction: Königstetten → Marswiese. Spherical distance: **{length / 1000:.3f} km**.",
              f"Difference from approximate 15.2 km: {(length - 15200) / 1000:+.3f} km.", "",
              "Map: `data/processed/route.svg`; geometry: `data/processed/route.geojson`.", "",
              "## Endpoint edge snaps", ""]
    for snap in snaps:
        report.append(f"- {snap['label']}: offset {snap['offset_m']:.2f} m, way {snap['way_id']}, edge {snap['edge_index']}, fraction {snap['fraction']:.6f}; lon/lat {snap['snapped_lon_lat']}.")
    report += ["", f"Route bounds (west, south, east, north): {properties['bounds_west_south_east_north']}.",
               "", "## Original sources", ""]
    report += [f"- `{s['source_file']}`; SHA256 `{s['sha256']}`; ODbL-1.0. "
               + (f"URL: {s['provenance']['url']}; requested UTC {s['provenance']['requested_at_utc']}."
                  if "provenance" in s else "") for s in properties["sources"]]
    if all("provenance" in s for s in properties["sources"]):
        source_bytes = sum(s["provenance"].get("received_bytes", s["provenance"].get("bytes", 0))
                           for s in properties["sources"])
        report += ["", f"Preserved original XML total: {source_bytes:,} bytes. URL/timestamp/checksum/license sidecars remain in `data/raw/osm/`.",
                   "Section operation attempts and byte accounting: `data/raw/osm/sections_*.json`; earlier `failed_*.json` evidence preserved."]
    report += ["", "## Ordered road segments", "", "| Road | Ref | Length (km) | OSM ways |", "|---|---|---:|---|"]
    report += [f"| {g['name']} | {g['ref']} | {g['length_m'] / 1000:.3f} | {', '.join(map(str, g['way_ids']))} |" for g in groups]
    report += ["", "## Limitations / acceptance blockers", ""] + ["- " + warning for warning in warnings]
    report += ["", f"Ways with additional tagged details to review: {flagged}.", "",
               "No Blender execution, game test, screenshot correspondence, or geographic raster validation was performed.",
               "Rebuild merge offline: `python3 scripts/acquire_osm_sections.py` (no network without `--acquire`).",
               "Rebuild route offline: `python3 scripts/route_osm.py --source data/interim/osm/merged.json`."]
    report_path = ROOT / "docs/validation/ROUTE_REPORT.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report) + "\n")
    print(f"Provisional path: {length / 1000:.3f} km; not screenshot-verified")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquire", action="store_true", help="explicitly allow up to three bounded network requests")
    parser.add_argument("--source", type=Path, help="saved .osm XML or Overpass/derived JSON; no network")
    args = parser.parse_args()
    if args.acquire and args.source:
        parser.error("Choose --acquire or --source, not both")
    if args.acquire:
        source, manifest = acquire()
        print(f"Saved {source} and {manifest}")
    elif args.source:
        source = args.source
    else:
        candidates = sorted(RAW.glob("roads_*.json"))
        if len(candidates) != 1:
            parser.error("Use --source for an existing extract, or explicitly --acquire; no implicit network requests")
        source = candidates[0]
    build(source.resolve())


if __name__ == "__main__":
    main()
