"""Persistent, bounded HTTP range acquisition. No response body is read on HTTP 200.

The ledger is the operation: restarting never resets its cumulative byte counter.
Use one process per cache directory. Completed and partial original bytes are kept.
"""
import hashlib
import http.client
import json
from pathlib import Path
import urllib.error
import urllib.request

from probe_raster_metadata import NoRedirect, ProbeError, validate_range

CAP = 500_000_000
MAX_RANGE = 8_000_000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


class RangeReader:
    def __init__(self, url, root, cap=CAP, opener=None):
        if not 0 < cap <= CAP:
            raise ValueError('invalid operation cap')
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'operation.json'
        self.opener = opener or urllib.request.build_opener(NoRedirect())
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            if self.state['url'] != url or self.state['cap'] != cap:
                raise ValueError('cache operation identity/cap changed')
        else:
            self.state = dict(url=url, cap=cap, actual_bytes=0, total=None,
                              etag=None, attempts=[], cache={})
            self.flush()

    def flush(self):
        save_json(self.path, self.state)

    def cached(self, start, size):
        key = f'{start}-{size}'
        entry = self.state['cache'].get(key)
        if entry is None:
            return None
        data = (self.root / entry['file']).read_bytes()
        if len(data) != size or digest(data) != entry['sha256']:
            raise ProbeError('cache checksum/size mismatch')
        return data

    @property
    def used_bytes(self):
        return self.state['actual_bytes'] + sum(self.state.get('external_bytes', {}).values())

    def charge_external(self, name, size):
        """Include separately preserved supporting-document transfers in this cap."""
        previous = self.state.setdefault('external_bytes', {}).get(name)
        if size < 0 or (previous is not None and previous != size):
            raise ProbeError('external transfer identity changed')
        self.state['external_bytes'][name] = size
        self.flush()
        if self.used_bytes > self.state['cap']:
            raise ProbeError('aggregate byte budget exhausted')

    def preflight(self, ranges, attempts=2):
        needed = sum(size for start, size in ranges if self.cached(start, size) is None)
        if self.used_bytes + attempts * needed > self.state['cap']:
            raise ProbeError('worst-case retries exceed aggregate operation budget')
        return needed

    def read(self, start, size):
        if start < 0 or not 0 < size <= MAX_RANGE:
            raise ProbeError('invalid/oversized range')
        if self.state['total'] is not None and start + size > self.state['total']:
            raise ProbeError('range beyond object')
        cached = self.cached(start, size)
        if cached is not None:
            return cached
        for retry in range(2):
            if self.used_bytes + size > self.state['cap']:
                raise ProbeError('aggregate byte budget exhausted')
            record = dict(offset=start, requested_bytes=size, actual_bytes=0)
            self.state['attempts'].append(record)
            attempt_id = len(self.state['attempts'])
            partial = self.root / f'attempt-{attempt_id:05d}.part'
            response = None
            data = bytearray()
            self.flush()
            try:
                headers = {'Range': f'bytes={start}-{start + size - 1}',
                           'Accept-Encoding': 'identity',
                           'User-Agent': 'Assetto-Exelberg-Terrain/1.0'}
                if self.state['etag']:
                    headers['If-Match'] = self.state['etag']
                response = self.opener.open(urllib.request.Request(self.state['url'], headers=headers), timeout=30)
                record.update(status=response.status, headers=dict(response.headers.items()))
                # Identity encoding is permissible; every other encoding is rejected.
                check_headers = dict(response.headers.items())
                if response.headers.get('Content-Encoding', '').lower() == 'identity':
                    check_headers = {k: v for k, v in check_headers.items() if k.lower() != 'content-encoding'}
                total = validate_range(response.status, check_headers, start, size, self.state['total'])
                etag = response.headers.get('ETag')
                if not etag or etag.startswith('W/'):
                    raise ProbeError('strong ETag required')
                if self.state['etag'] is not None and self.state['etag'] != etag:
                    raise ProbeError('ETag changed')
                self.state.update(total=total, etag=etag)
                self.flush()
                with partial.open('wb') as out:
                    while len(data) < size:
                        try:
                            block = response.read(min(65536, size - len(data)))
                        except http.client.IncompleteRead as exc:
                            block = exc.partial
                        if not block:
                            break
                        data.extend(block)
                        # Charge returned bytes even if preserving them later fails.
                        self.state['actual_bytes'] += len(block)
                        record['actual_bytes'] = len(data)
                        self.flush()
                        out.write(block)
                        out.flush()
                if len(data) != size:
                    raise OSError('short range response')
                name = f'range-{start}-{size}.bin'
                partial.replace(self.root / name)
                entry = dict(file=name, sha256=digest(data))
                self.state['cache'][f'{start}-{size}'] = entry
                record.update(entry)
                return bytes(data)
            except Exception as exc:
                record['error'] = str(exc)
                if isinstance(exc, urllib.error.HTTPError):
                    exc.close()
                # Protocol/object changes fail closed, not retried.
                if isinstance(exc, (ProbeError, urllib.error.HTTPError)) or retry == 1:
                    raise
            finally:
                if response is not None:
                    response.close()
                record['sha256'] = digest(data)
                if partial.exists():
                    record['partial_file'] = partial.name
                self.flush()
        raise AssertionError('unreachable')
