"""Generate independently random assay matrices inside the ProteinPaint build."""
import json
from pathlib import Path
import random
import sqlite3
import h5py
import numpy as np
import subprocess

root = Path('/home/root/pp/tp')
cases = json.loads((root / 'cases.json').read_text())
expression = json.loads((root / 'expression.json').read_text())
genes = list(expression)
samples = [c['sample_id'] for c in cases]
rng = random.Random(1783)


def matrix(path, names, values):
    with h5py.File(path, 'w') as handle:
        text = h5py.string_dtype('utf-8')
        handle.create_dataset('item', data=genes, dtype=text)
        handle.create_dataset('samples', data=names, dtype=text)
        handle.create_dataset('matrix', data=np.array(values, dtype=np.float32))


matrix(root / 'expression.h5', samples, [[expression[g][s] for s in samples] for g in genes])
matrix(root / 'counts.h5', samples, [[rng.randint(10, 10000) for s in samples] for g in genes])
(root / 'singlecell/umap').mkdir(parents=True, exist_ok=True)
(root / 'singlecell/expression').mkdir(parents=True, exist_ok=True)
(root / 'singlecell/meta').mkdir(parents=True, exist_ok=True)
(root / 'singlecell/pseudobulk').mkdir(parents=True, exist_ok=True)
lineages = ['Plasma', 'T', 'B', 'Myeloid']
combined_cells, combined_values, fractions = [], [[] for _ in genes], []
pseudobulk = {key: {method: [[] for _ in genes] for method in ('mean', 'percent', 'total')} for key in lineages}
with (root / 'singlecell/meta/combined.tsv').open('w') as meta:
    meta.write('cell\tsample\tsubcluster\tcompartment\tcell_type\tlineage\tx\ty\n')
    for sample in samples:
        cells = [f'{sample}-CELL-{number:04d}' for number in range(1, 81)]
        # All categories have cells, with independent random proportions per sample.
        labels = lineages + rng.choices(lineages, weights=[3, 2, 1, 1], k=len(cells) - len(lineages))
        values = [[round(rng.uniform(0, 8), 3) if rng.random() > 0.15 else 0 for _ in cells] for _ in genes]
        fractions.append({key: labels.count(key) / len(cells) for key in lineages})
        with (root / f'singlecell/umap/{sample}_umap.txt').open('w') as output:
            output.write('cell\tx\ty\tcell_type\n')
            for cell, label in zip(cells, labels):
                cluster = lineages.index(label)
                x, y = rng.gauss(cluster % 2 * 5, 1), rng.gauss(cluster // 2 * 5, 1)
                output.write(f'{cell}\t{x:.4f}\t{y:.4f}\tSynthetic {label} cells\n')
                meta.write(f'{cell}\t{sample}\tSynthetic {label}-{rng.randint(1, 3)}\tSynthetic immune\tSynthetic {label} cells\t{label}\t{x:.4f}\t{y:.4f}\n')
        matrix(root / f'singlecell/expression/{sample}.h5', cells, values)
        combined_cells.extend(cells)
        for index, row in enumerate(values):
            combined_values[index].extend(row)
            for label in lineages:
                selected = [value for value, category in zip(row, labels) if category == label]
                pseudobulk[label]['mean'][index].append(sum(selected) / len(selected))
                pseudobulk[label]['total'][index].append(sum(selected))
                pseudobulk[label]['percent'][index].append(100 * sum(value > 0 for value in selected) / len(selected))
matrix(root / 'singlecell/expression/combined.h5', combined_cells, combined_values)
for label, methods in pseudobulk.items():
    for method, values in methods.items():
        matrix(root / f'singlecell/pseudobulk/{label}.{method}.h5', samples, values)
with sqlite3.connect(root / 'termdb.sqlite') as db:
    for order, label in enumerate(lineages, 100):
        term = {'id': label, 'name': f'Synthetic {label} cell fraction', 'type': 'float', 'isleaf': True}
        db.execute('INSERT OR REPLACE INTO terms VALUES (?,?,?,?,?,?,?)',
                   (label, term['name'], None, json.dumps(term), order, 'float', 1))
        db.execute('INSERT INTO alltermsbyorder VALUES (?,?)', ('', label))
        db.execute('INSERT INTO subcohort_terms VALUES (?,?,?,?,?)', ('', label, len(samples), 'float', ''))
        db.executemany('INSERT INTO anno_float VALUES (?,?,?)', [(index, label, values[label]) for index, values in enumerate(fractions, 1)])

with sqlite3.connect(root / 'genes.sqlite') as db:
    models = [(name, json.loads(model)) for name, model in db.execute('select name,genemodel from genes')]
with (root / 'genes.bedj').open('w') as output:
    for name, model in sorted(models, key=lambda pair: (pair[1]['chr'], pair[1]['start'])):
        output.write(f"{model['chr']}\t{model['start']}\t{model['stop']}\t{json.dumps(model)}\n")
subprocess.run(['bgzip', '-f', str(root / 'genes.bedj')], check=True)
subprocess.run(['tabix', '-f', '-p', 'bed', str(root / 'genes.bedj.gz')], check=True)
with (root / 'cnv.tsv').open('w') as output:
    output.write('#sample ' + ' '.join(samples) + '\n')
    for name, model in sorted(models, key=lambda pair: (pair[1]['chr'], pair[1]['start'])):
        for index, sample in enumerate(samples, 1):
            value = {'dt': 4, 'value': rng.choice([-0.8, 0.8]), 'sample': index}
            output.write(f"{model['chr']}\t{model['start']}\t{model['stop']}\t{json.dumps(value)}\n")
subprocess.run(['bgzip', '-f', str(root / 'cnv.tsv')], check=True)
subprocess.run(['tabix', '-f', '-p', 'bed', str(root / 'cnv.tsv.gz')], check=True)
