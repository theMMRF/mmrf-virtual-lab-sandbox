from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('generator', Path(__file__).resolve().parents[1] / 'synthetic/generate.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class SyntheticIntegrity(unittest.TestCase):
    def test_all_id_spaces_and_reproducibility(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            cases, files, variants = generator.generate(first, count=20)
            generator.generate(second, count=20)
            paths = sorted(p.name for p in Path(first).iterdir())
            self.assertEqual(paths, sorted(p.name for p in Path(second).iterdir()))
            for name in paths:
                self.assertEqual((Path(first) / name).read_bytes(), (Path(second) / name).read_bytes(), name)
            ids = {c['case_id'] for c in cases}
            samples = {c['sample_id'] for c in cases}
            self.assertTrue(all(c['synthetic'] for c in cases))
            self.assertTrue(all(v['case_id'] in ids and v['sample_id'] in samples for v in variants))
            self.assertTrue(all(f['cases'][0]['case_id'] in ids for f in files))
            with closing(sqlite3.connect(Path(first) / 'termdb.sqlite')) as db:
                self.assertEqual(samples, {r[0] for r in db.execute('select name from sampleidmap')})
                self.assertEqual(len(cases), db.execute('select count(*) from survival').fetchone()[0])
            with closing(sqlite3.connect(Path(first) / 'genes.sqlite')) as db:
                for alias in ('c-Myc', 'ENSG00000136997', 'ENST00000621592', 'NM_002467'):
                    self.assertEqual('MYC', db.execute('SELECT name FROM genealias WHERE alias=?', (alias,)).fetchone()[0])
            header = next(line for line in (Path(first) / 'variants.vcf').read_text().splitlines() if line.startswith('#CHROM'))
            self.assertEqual(samples, set(header.split('\t')[9:]))
            reference = {}
            for line in (Path(first) / 'synthetic.fa').read_text().splitlines():
                if line.startswith('>'):
                    chrom = line[1:]
                    reference[chrom] = ''
                else:
                    reference[chrom] += line
            for variant in variants:
                self.assertEqual(reference[variant['chr']][variant['pos'] - 1], variant['ref'])
            for line in (Path(first) / 'variants.vcf').read_text().splitlines():
                if not line.startswith('#'):
                    self.assertEqual(len(line.split('\t')[7].removeprefix('CSQ=').split('|')), 12)
            for f in files:
                sequence = (Path(first) / f['file_name']).read_text().splitlines()[1]
                self.assertEqual(set(sequence), set('ACGT'))

    def test_demographic_groups_support_survival_and_gene_comparisons(self):
        with tempfile.TemporaryDirectory() as out:
            cases, _, variants = generator.generate(out)
            for gender in ('male', 'female'):
                for race in ('white', 'black or african american', 'asian'):
                    selected = {c['case_id'] for c in cases if c['gender'] == gender and c['race'] == race}
                    self.assertGreaterEqual(len(selected), 150)
                    for symbol, *_ in generator.GENES:
                        mutated = {v['case_id'] for v in variants if v['symbol'] == symbol and v['case_id'] in selected}
                        self.assertGreaterEqual(len(mutated), 10, (gender, race, symbol))
                        self.assertGreaterEqual(len(selected - mutated), 10, (gender, race, symbol))


if __name__ == '__main__':
    unittest.main()
