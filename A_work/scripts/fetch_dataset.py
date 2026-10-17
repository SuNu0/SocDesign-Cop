"""Download and safely extract the unmodified Speech Commands V2 archive."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile
import time
import urllib.request

URL = 'https://storage.googleapis.com/download.tensorflow.org/data/speech_commands_v0.02.tar.gz'

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    archive = a.out / 'speech_commands_v0.02.tar.gz'
    if not archive.exists():
        partial = archive.with_suffix('.gz.partial')
        offset = partial.stat().st_size if partial.exists() else 0
        req = urllib.request.Request(URL, headers={'Range': 'bytes=%d-' % offset} if offset else {})
        with urllib.request.urlopen(req, timeout=90) as response:
            append = offset and response.status == 206
            total = int(response.headers.get('Content-Length', 0)) + (offset if append else 0)
            done = offset if append else 0
            last = time.time()
            with partial.open('ab' if append else 'wb') as f:
                while True:
                    block = response.read(4*1024*1024)
                    if not block:
                        break
                    f.write(block)
                    done += len(block)
                    if time.time()-last > 15:
                        print('download %d / %d MiB' % (done//2**20, total//2**20), flush=True)
                        last = time.time()
            if total and done != total:
                raise RuntimeError('Incomplete download')
        partial.replace(archive)
    digest = hashlib.sha256()
    with archive.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024), b''):
            digest.update(b)
    dest = a.out / 'speech_commands_v0.02'
    stamp = a.out / 'dataset_manifest.json'
    if not stamp.exists():
        dest.mkdir(exist_ok=True)
        root = dest.resolve()
        n = 0
        with tarfile.open(archive, 'r:gz') as tar:
            for member in tar:
                target = (root/member.name).resolve()
                if os.path.commonpath([str(root), str(target)]) != str(root):
                    raise ValueError('Unsafe archive path')
                if not (member.isdir() or member.isfile()):
                    raise ValueError('Unexpected archive link/type')
                tar.extract(member, dest)
                n += 1
                if n % 10000 == 0:
                    print('extracted %d entries' % n, flush=True)
        stamp.write_text(json.dumps({'url':URL, 'archive_sha256':digest.hexdigest(),
            'entries':n, 'dataset':str(dest.resolve())}, indent=2), encoding='utf-8')
    print(stamp.read_text(encoding='utf-8'), flush=True)

if __name__ == '__main__':
    main()
