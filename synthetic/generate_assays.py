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
for sample in samples:
    cells = [f'SYNTH-CELL-{number:04d}' for number in range(1, 81)]
    with (root / f'singlecell/umap/{sample}_umap.txt').open('w') as output:
        output.write('cell\tx\ty\tcell_type\n')
        for number, cell in enumerate(cells):
            output.write(f'{cell}\t{rng.gauss(number % 2 * 3, 1):.4f}\t{rng.gauss(0, 1):.4f}\tSynthetic cell {number % 2 + 1}\n')
    matrix(root / f'singlecell/expression/{sample}.h5', cells, [[rng.uniform(0, 20) for _ in cells] for _ in genes])

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
