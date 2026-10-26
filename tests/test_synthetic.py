from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import gzip
import hashlib
from collections import Counter

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
                self.assertEqual(reference[variant['chr']][variant['pos'] - 1:variant['pos'] - 1 + len(variant['ref'])], variant['ref'])
            for line in (Path(first) / 'variants.vcf').read_text().splitlines():
                if not line.startswith('#'):
                    self.assertEqual(len(line.split('\t')[7].removeprefix('CSQ=').split('|')), 12)
            for f in files:
                payload = (Path(first) / f['file_name']).read_bytes()
                self.assertEqual(f['file_size'], len(payload))
                self.assertEqual(f['md5sum'], hashlib.md5(payload, usedforsecurity=False).hexdigest())
                if f['data_format'] == 'FASTA':
                    self.assertEqual(set(payload.decode().splitlines()[1]), set('ACGT'))
                if f['data_format'] == 'BAM':
                    self.assertTrue(gzip.decompress(payload).startswith(b'BAM\x01'))

    def test_demographic_groups_support_survival_and_gene_comparisons(self):
        with tempfile.TemporaryDirectory() as out:
            cases, files, variants = generator.generate(out)
            self.assertEqual(len({c['project_id'] for c in cases}), 2)
            self.assertNotRegex(json.dumps(cases), r'Synthetic [AB]\b')
            self.assertEqual({c['cgs_risk_key_criteria']['cgs_risk_category'] for c in cases}, {'High risk', 'Standard risk'})
            self.assertEqual({label for c in cases for label in c['cgs_risk_key_criteria']['cgs_risk_criteria']}, set(generator.CGS_CRITERIA))
            for case in cases:
                risk = case['cgs_risk_key_criteria']
                self.assertEqual(risk['cgs_risk_category'] == 'High risk', bool(risk['cgs_risk_criteria']))
                regimen = case['administered_regimen_lines'][0]
                self.assertEqual(dict(generator.REGIMENS)[regimen['regimen_short_name']], regimen['regimen_name'])
                self.assertEqual(regimen['first_line'] == 'Yes', regimen['line'] == 1)
            self.assertEqual({v['class'] for v in variants}, {'M', 'N', 'P', 'F', 'D', 'I', 'S'})
            for field in ('data_format', 'data_type', 'data_category', 'experimental_strategy'):
                self.assertGreaterEqual(len({f[field] for f in files}), 3)
            self.assertGreaterEqual(len({f['downstream_analyses'][0]['workflow_type'] for f in files}), 3)
            # One shared ID and one VCF row per variant, with every carrier on it.
            carriers = {}
            for variant in variants:
                carriers.setdefault(variant['ssm_id'], set()).add(variant['sample_id'])
            rows = [line.split('\t') for line in (Path(out) / 'variants.vcf').read_text().splitlines() if not line.startswith('#')]
            self.assertEqual(len(rows), len(carriers))
            self.assertTrue(all({c['sample_id'] for c, gt in zip(cases, row[9:]) if gt == '0/1'} == carriers[row[2]] for row in rows))
            for gender in ('male', 'female'):
                for race in ('white', 'black or african american', 'asian'):
                    selected = {c['case_id'] for c in cases if c['gender'] == gender and c['race'] == race}
                    self.assertGreaterEqual(len(selected), 150)
                    for risk in ('High risk', 'Standard risk'):
                        self.assertGreaterEqual(sum(c['case_id'] in selected and c['cgs_risk_key_criteria']['cgs_risk_category'] == risk for c in cases), 10)
                    for symbol, *_ in generator.GENES:
                        mutated = {v['case_id'] for v in variants if v['symbol'] == symbol and v['case_id'] in selected}
                        self.assertGreaterEqual(len(mutated), 10, (gender, race, symbol))
                        self.assertGreaterEqual(len(selected - mutated), 10, (gender, race, symbol))
                        recurrent = Counter(v['ssm_id'] for v in variants if v['symbol'] == symbol and v['case_id'] in selected)
                        self.assertGreaterEqual(recurrent.most_common(1)[0][1], 10, (gender, race, symbol))


if __name__ == '__main__':
    unittest.main()
