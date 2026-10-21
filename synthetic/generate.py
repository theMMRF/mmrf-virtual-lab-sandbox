"""Generate fixtures from a seed only. No source-data input is accepted."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sqlite3

GENES = [
    ("KRAS", "ENSG00000133703", "chr12", 10000),
    ("NRAS", "ENSG00000213281", "chr1", 20000),
    ("TP53", "ENSG00000141510", "chr17", 30000),
    ("BRAF", "ENSG00000157764", "chr7", 40000),
    ("DIS3", "ENSG00000150907", "chr13", 50000),
]
COHORT_FIELDS = json.loads((Path(__file__).resolve().parents[1] / 'config/cohort-fields.json').read_text())


def fill_field(record, path, value):
    parts = path.split('.')
    current = record
    for part in parts[:-1]:
        if part not in current:
            current[part] = [{}] if part in ('diagnoses', 'samples', 'files', 'follow_ups', 'family_histories', 'bone_assessments', 'administered_regimen_lines') else {}
        current = current[part]
        if isinstance(current, list):
            current = current[0]
    current.setdefault(parts[-1], value)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def generate(out, count=60, seed=42):
    if not 10 <= count <= 1000:
        raise ValueError("Choose between 10 and 1000 synthetic cases")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    records, files, variants = [], [], []
    for number in range(1, count + 1):
        cid = f"SYNTH-CASE-{number:04d}"
        sid = f"SYNTH-SAMPLE-{number:04d}"
        age = rng.randint(40, 85)
        days = rng.randint(180, 3500)
        vital = rng.choice(["Alive", "Alive", "Dead"])
        project = {"project_id": "SYNTHETIC-MM", "name": "Synthetic myeloma", "program": {"name": "SYNTHETIC"},
                   "primary_site": "Bone Marrow", "disease_type": "Multiple Myeloma"}
        sample = {"sample_id": sid, "submitter_id": sid, "sample_type": "Primary Tumor", "tissue_type": "Tumor",
                  "tumor_descriptor": "Primary", "specimen_type": "Bone Marrow", "preservation_method": "Frozen"}
        case = {"id": cid, "case_id": cid, "submitter_id": cid, "project_id": "SYNTHETIC-MM", "project": project,
                "batch_id": "SYNTHETIC", "primary_site": "Bone Marrow", "disease_type": "Multiple Myeloma",
                "index_date": "Diagnosis", "gender": rng.choice(["male", "female"]), "race": rng.choice(["white", "black or african american", "asian"]),
                "ethnicity": rng.choice(["hispanic or latino", "not hispanic or latino"]), "age_at_index": age,
                "age_at_diagnosis": age * 365, "days_to_birth": -age * 365, "vital_status": vital,
                "days_to_death": days if vital == "Dead" else None, "days_to_last_follow_up": days,
                "primary_diagnosis": "Multiple myeloma", "therapeutic_agents": rng.choice(["Synthetic regimen A", "Synthetic regimen B"]),
                "auth_resource_path": "/programs/SYNTHETIC/projects/MM", "authz": ["/programs/SYNTHETIC/projects/MM"],
                "samples": [sample], "sample_id": sid, "sample_ids": [sid], "synthetic": True}
        case["demographic"] = {k: case[k] for k in ["gender", "race", "ethnicity", "vital_status", "days_to_birth", "days_to_death"]}
        case["diagnoses"] = [{"age_at_diagnosis": age, "days_to_last_follow_up": days,
                               "primary_diagnosis": case["primary_diagnosis"], "treatments": [{"therapeutic_agents": case["therapeutic_agents"]}]}]
        for path, spec in COHORT_FIELDS.items():
            value = rng.randint(1, 20) if spec['type'] in ('numeric_range', 'days') else rng.choice(['Synthetic A', 'Synthetic B'])
            if spec['type'].startswith('age'):
                value = age * 365
            elif spec['type'] == 'year':
                value = 2020 + number % 5
            fill_field(case, path, value)
        case['outcomes'] = {'censor_os': int(vital == 'Dead'), 'censor_pfs': int(vital == 'Dead'),
                            'surivival_time_os': days, 'survival_time_pfs': days}
        records.append(case)
        sequence = "".join(rng.choice("ACGT") for _ in range(100))
        filename = f"{sid}.synthetic.fasta"
        payload = f">{sid} SYNTHETIC RANDOM SEQUENCE; NOT BIOLOGICAL DATA\n{sequence}\n"
        (out / filename).write_text(payload)
        fid = f"SYNTH-FILE-{number:04d}"
        files.append({"id": fid, "file_id": fid, "file_name": filename, "file_size": len(payload),
                      "md5sum": hashlib.md5(payload.encode(), usedforsecurity=False).hexdigest(),
                      "data_category": "Sequencing Reads", "data_type": "Synthetic sequence", "data_format": "FASTA",
                      "experimental_strategy": "WGS", "wgs_coverage": "30x", "platform": "Synthetic sequencer",
                      "downstream_analyses": [{"workflow_type": "Synthetic workflow"}],
                      "access": "open", "state": "released", "acl": ["SYNTHETIC-MM"], "project_id": "SYNTHETIC-MM",
                      "auth_resource_path": case["auth_resource_path"], "cases": [case], "synthetic": True})
    for symbol, gid, chrom, start in GENES:
        for number, case in enumerate(records, 1):
            if rng.random() < 0.35:
                variants.append({"case_id": case["case_id"], "sample_id": case["sample_id"], "sample": number,
                                 "gene_id": gid, "symbol": symbol, "chr": chrom, "pos": start + number,
                                 "ref": "A", "alt": "T", "class": "M", "mname": f"p.X{number}Y"})
    write_json(out / "cases.json", records)
    write_json(out / "files.json", files)
    write_json(out / "variants.json", variants)
    write_json(out / "provenance.json", {"synthetic": True, "generator_version": 1, "seed": seed,
                                         "cases": count, "source": "Seeded pseudorandom generation; no patient inputs"})
    make_termdb(out, records)
    make_gene_db(out)
    make_vcf(out, records, variants)
    write_json(out / "expression.json", {g[0]: {c["sample_id"]: round(rng.uniform(0.1, 100), 3) for c in records} for g in GENES})
    with (out / 'synthetic.fa').open('w') as fasta, (out / 'synthetic.fa.fai').open('w') as fai:
        for chrom in sorted({g[2] for g in GENES}):
            fasta.write(f'>{chrom}\n')
            offset = fasta.tell()
            sequence = [rng.choice('ACGT') for _ in range(100000)]
            for variant in variants:
                if variant['chr'] == chrom:
                    sequence[variant['pos'] - 1] = variant['ref']
            sequence = ''.join(sequence)
            for start in range(0, len(sequence), 80):
                fasta.write(sequence[start:start + 80] + '\n')
            fai.write(f'{chrom}\t100000\t{offset}\t80\t81\n')
    with (out / 'bulk-umap.tsv').open('w') as scatter:
        scatter.write('sample\tx\ty\n')
        for case in records:
            scatter.write(f"{case['sample_id']}\t{rng.gauss(0, 2):.4f}\t{rng.gauss(0, 2):.4f}\n")
    return records, files, variants


def make_termdb(out, cases):
    path = out / "termdb.sqlite"
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    db.executescript("""
CREATE TABLE terms (id TEXT PRIMARY KEY, name TEXT, parent_id TEXT, jsondata TEXT, child_order INTEGER, type TEXT, isleaf INTEGER);
CREATE TABLE ancestry (term_id TEXT, ancestor_id TEXT);
CREATE TABLE alltermsbyorder (group_name TEXT, id TEXT);
CREATE TABLE subcohort_terms (cohort TEXT, term_id TEXT, count INTEGER, included_types TEXT, child_types TEXT);
CREATE TABLE subcohort_samples (subcohort TEXT, sample INTEGER);
CREATE TABLE cohorts (cohort TEXT, name TEXT, sample_count INTEGER);
CREATE TABLE features (idfeature INTEGER, name TEXT);
CREATE TABLE cohort_features (cohort TEXT, idfeature INTEGER, value TEXT);
CREATE TABLE termhtmldef (id TEXT, jsonhtml TEXT);
CREATE TABLE sampleidmap (id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE anno_categorical (sample INTEGER, term_id TEXT, value TEXT);
CREATE TABLE anno_integer (sample INTEGER, term_id TEXT, value INTEGER);
CREATE TABLE anno_float (sample INTEGER, term_id TEXT, value REAL);
CREATE TABLE survival (sample INTEGER, term_id TEXT, tte REAL, exit_code INTEGER);
CREATE TABLE buildDate (date TEXT);
INSERT INTO buildDate VALUES ('synthetic-v1');
""")
    fields = [("gender", "Gender", "categorical"), ("race", "Race", "categorical"),
              ("vital_status", "Vital status", "categorical"), ("age_at_index", "Age at diagnosis", "integer"),
              ("therapeutic_agents", "Synthetic treatment", "categorical")]
    for order, (key, label, kind) in enumerate(fields):
        term = {"id": key, "name": label, "type": kind, "isleaf": True}
        if kind == "categorical":
            term["values"] = {v: {"label": v} for v in sorted({c[key] for c in cases})}
        db.execute("INSERT INTO terms VALUES (?,?,?,?,?,?,?)", (key, label, None, json.dumps(term), order, kind, 1))
        db.execute("INSERT INTO alltermsbyorder VALUES (?,?)", ("", key))
        db.execute("INSERT INTO subcohort_terms VALUES (?,?,?,?,?)", ("", key, len(cases), kind, ""))
        for number, case in enumerate(cases, 1):
            db.execute(f"INSERT INTO anno_{kind} VALUES (?,?,?)", (number, key, case[key]))
    term = {"id": "overall_survival", "name": "Synthetic overall survival", "type": "survival", "isleaf": True,
            "unit": "years", "values": {"0": {"label": "Censored"}, "1": {"label": "Death"}}}
    db.execute("INSERT INTO terms VALUES (?,?,?,?,?,?,?)", (term["id"], term["name"], None, json.dumps(term), 9, "survival", 1))
    db.execute("INSERT INTO alltermsbyorder VALUES (?,?)", ("", term["id"]))
    db.execute("INSERT INTO subcohort_terms VALUES (?,?,?,?,?)", ("", term["id"], len(cases), "survival", ""))
    for number, case in enumerate(cases, 1):
        db.execute("INSERT INTO sampleidmap VALUES (?,?)", (number, case["sample_id"]))
        db.execute("INSERT INTO survival VALUES (?,?,?,?)", (number, term["id"], case["days_to_last_follow_up"] / 365.25, int(case["vital_status"] == "Dead")))
    db.commit()
    db.close()


def make_gene_db(out):
    path = out / "genes.sqlite"
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    db.executescript("""
CREATE TABLE genes (name TEXT COLLATE NOCASE, isoform TEXT COLLATE NOCASE, isdefault INTEGER, genemodel TEXT);
CREATE TABLE genealias (alias TEXT COLLATE NOCASE, name TEXT COLLATE NOCASE);
CREATE TABLE refseq2ensembl (ensembl TEXT, refseq TEXT);
CREATE TABLE gene2coord (name TEXT COLLATE NOCASE, chr TEXT, start INTEGER, stop INTEGER);
CREATE TABLE gene2canonicalisoform (gene TEXT COLLATE NOCASE, isoform TEXT);
CREATE TABLE codingGenes (name TEXT COLLATE NOCASE);
""")
    for symbol, gid, chrom, start in GENES:
        model = {"name": symbol, "isoform": gid, "chr": chrom, "start": start, "stop": start + 2000,
                 "strand": "+", "codingstart": start, "codingstop": start + 2000,
                 "exon": [[start, start + 2000]], "coding": [[start, start + 2000]], "isdefault": True}
        db.execute("INSERT INTO genes VALUES (?,?,?,?)", (symbol, gid, 1, json.dumps(model)))
        db.execute("INSERT INTO genealias VALUES (?,?)", (gid, symbol))
        db.execute("INSERT INTO gene2coord VALUES (?,?,?,?)", (symbol, chrom, start, start + 2000))
        db.execute("INSERT INTO gene2canonicalisoform VALUES (?,?)", (symbol, gid))
        db.execute("INSERT INTO codingGenes VALUES (?)", (symbol,))
    db.commit()
    db.close()


def make_vcf(out, cases, variants):
    with (out / "variants.vcf").open("w") as handle:
        handle.write('##fileformat=VCFv4.2\n##source=MMRF-synthetic-generator\n')
        for chrom in sorted({g[2] for g in GENES}):
            handle.write(f'##contig=<ID={chrom},length=100000>\n')
        handle.write('##INFO=<ID=CSQ,Number=.,Type=String,Description="Synthetic annotations. Format: Allele|Consequence|IMPACT|SYMBOL|Gene|Feature_type|Feature|BIOTYPE|EXON|INTRON|HGVSc|HGVSp">\n')
        handle.write('##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">\n')
        handle.write('#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t' + '\t'.join(c['sample_id'] for c in cases) + '\n')
        for var in sorted(variants, key=lambda v: (v['chr'], v['pos'])):
            csq = f"T|missense_variant|MODERATE|{var['symbol']}|{var['gene_id']}|Transcript|{var['gene_id']}|protein_coding|1|||{var['mname']}"
            genotypes = ['0/1' if c['sample_id'] == var['sample_id'] else './.' for c in cases]
            handle.write(f"{var['chr']}\t{var['pos']}\t.\tA\tT\t100\tPASS\tCSQ={csq}\tGT\t" + '\t'.join(genotypes) + '\n')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="generated")
    parser.add_argument("--cases", type=int, default=60)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    generate(args.out, args.cases, args.seed)
