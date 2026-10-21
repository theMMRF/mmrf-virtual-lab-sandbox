"""Reseed after disposable Kubernetes search storage is recreated."""
import os
import subprocess
import time
import urllib.request

base = os.environ.get('GEN3_ES_ENDPOINT', 'http://elasticsearch:9200')
if base != 'http://elasticsearch:9200':
    raise SystemExit('Only the sandbox search service is supported')
while True:
    try:
        with urllib.request.urlopen(base + '/sandbox_seed_complete/_count', timeout=5):
            pass
    except OSError:
        subprocess.run(['python', 'seed_es.py'], check=True)
    time.sleep(10)
