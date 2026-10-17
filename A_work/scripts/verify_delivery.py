"""Verify the frozen source/evidence hashes without rerunning ML inference."""
import hashlib
import json
from pathlib import Path

def main():
    root=Path(__file__).resolve().parents[1]
    manifest=json.loads((root/'reports'/'delivery_manifest.json').read_text(encoding='utf-8'))
    for name,expected in manifest['files_sha256'].items():
        p=(root/name).resolve()
        if root not in p.parents:raise ValueError('Invalid manifest path: '+name)
        digest=hashlib.sha256(p.read_bytes()).hexdigest()
        if digest!=expected:raise ValueError('Hash mismatch: '+name)
    print('A_DELIVERY_HASHES_VERIFIED count=%d'%len(manifest['files_sha256']))

if __name__=='__main__':main()
