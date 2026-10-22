"""Keep Kubernetes Guppy's GraphQL schema aligned with seeded documents."""

from contextlib import redirect_stdout
import importlib.util
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fixture_generator', ROOT / 'synthetic/generate.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class HelmSchemaParity(unittest.TestCase):
    def test_chart_schema_matches_generated_graphql_contract(self):
        """Exercise the seeder without a server; detect stale chart field shapes."""
        def fake_search(request, timeout=None):
            url = urlsplit(request.full_url)
            self.assertEqual(url.netloc, 'elasticsearch:9200')
            data = {'_source': {'fingerprint': fingerprint}} if url.path == '/sandbox_seed_complete/_doc/ready' else {'errors': False}
            return io.BytesIO(json.dumps(data).encode())

        with tempfile.TemporaryDirectory() as directory:
            generator.generate(directory, count=20)
            fingerprint = hashlib.sha256(b''.join((Path(directory) / name).read_bytes()
                                                  for name in ('cases.json', 'files.json', 'variants.json'))).hexdigest()
            with patch.dict(os.environ, DATA_DIR=directory, GEN3_ES_ENDPOINT='http://elasticsearch:9200'), \
                    patch('urllib.request.urlopen', side_effect=fake_search), redirect_stdout(io.StringIO()):
                runpy.run_path(str(ROOT / 'synthetic/seed_es.py'), run_name='__main__')
            generated = json.loads((Path(directory) / 'guppy.json').read_text())
        chart = json.loads((ROOT / 'helm/files/guppy.json').read_text())
        self.assertEqual(chart, generated, 'Regenerate helm/files/guppy.json when fixture field shapes change')
        project_arrays = next(item['array'] for item in chart['arrayConfig'] if item['index'] == 'sandbox_project')
        self.assertTrue({'disease_type', 'primary_site', 'summary.data_categories',
                         'summary.experimental_strategies'}.issubset(project_arrays))


if __name__ == '__main__':
    unittest.main()
