"""Generate fixtures from a seed only. No source-data input is accepted."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import struct
import zlib
from collections import defaultdict

GENES = [
    ("KRAS", "ENSG00000133703", "chr12", 10000),
    ("NRAS", "ENSG00000213281", "chr1", 20000),
    ("TP53", "ENSG00000141510", "chr17", 30000),
    ("BRAF", "ENSG00000157764", "chr7", 40000),
    ("DIS3", "ENSG00000150907", "chr13", 50000),
    ("MYC", "ENSG00000136997", "chr8", 60000),
]
COHORT_FIELDS = json.loads((Path(__file__).resolve().parents[1] / 'config/cohort-fields.json').read_text())
# Public terminology only; fixture assignments are unrelated to patient data.
# IMS/IMWG consensus: https://pubmed.ncbi.nlm.nih.gov/40489728/
CGS_CRITERIA = (
    'del(17p) and/or TP53 mutation',
    't(4;14), t(14;16), or t(14;20) with 1q+ and/or del(1p32)',
    'Monoallelic del(1p32) with 1q+, or biallelic del(1p32)',
    'Beta-2 microglobulin >=5.5 mg/L with creatinine <1.2 mg/dL',
)
REGIMENS = (
    ('VRd', 'Bortezomib, lenalidomide, dexamethasone'),
    ('DRd', 'Daratumumab, lenalidomide, dexamethasone'),
    ('KRd', 'Carfilzomib, lenalidomide, dexamethasone'),
    ('VCd', 'Bortezomib, cyclophosphamide, dexamethasone'),
)
FILE_PROFILES = [
    ('fasta', 'FASTA', 'WGS', 'Sequencing Reads', 'Synthetic sequence', 'Synthetic assembly'),
    ('bam', 'BAM', 'WGS', 'Sequencing Reads', 'Aligned Reads', 'Synthetic alignment'),
    ('fastq', 'FASTQ', 'WXS', 'Sequencing Reads', 'Unaligned Reads', 'Synthetic read processing'),
    ('tsv', 'TSV', 'RNA-Seq', 'Transcriptome Profiling', 'Gene Expression Quantification', 'Synthetic expression counts'),
    ('vcf', 'VCF', 'WGS', 'Simple Nucleotide Variation', 'Annotated Somatic Mutation', 'Synthetic variant calling'),
    ('csv', 'CSV', 'scRNA-Seq', 'Transcriptome Profiling', 'Cell Type Quantification', 'Synthetic cell clustering'),
]


def bam_payload(sample, sequence):
    """A valid tiny BGZF BAM with one fabricated unmapped read; no reference data."""
    header = f'@HD\tVN:1.6\tSO:unsorted\n@RG\tID:{sample}\tSM:{sample}\n@CO\tSYNTHETIC TEST DATA\n'.encode()
    name = (sample + '\0').encode()
    alphabet = {'A': 1, 'C': 2, 'G': 4, 'T': 8}
    encoded = bytes((alphabet[a] << 4) | alphabet[b] for a, b in zip(sequence[::2], sequence[1::2]))
    record = struct.pack('<iiIIiiii', -1, -1, (4680 << 16) | len(name), 4 << 16, len(sequence), -1, -1, 0)
    record += name + encoded + bytes([255]) * len(sequence)
    data = b'BAM\x01' + struct.pack('<i', len(header)) + header + struct.pack('<i', 0)
    data += struct.pack('<i', len(record)) + record
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(data) + compressor.flush()
    bgzf = bytes.fromhex('1f8b08040000000000ff060042430200') + struct.pack('<H', len(compressed) + 25)
    bgzf += compressed + struct.pack('<II', zlib.crc32(data), len(data))
    return bgzf + bytes.fromhex('1f8b08040000000000ff0600424302001b00030000000000000000000000')


def file_payload(extension, sample, sequence):
    if extension == 'bam':
        return bam_payload(sample, sequence)
    text = {
        'fasta': f'>{sample} SYNTHETIC RANDOM SEQUENCE; NOT BIOLOGICAL DATA\n{sequence}\n',
        'fastq': f'@{sample} SYNTHETIC\n{sequence}\n+\n' + 'I' * len(sequence) + '\n',
        'tsv': 'gene_id\tsample_id\tsynthetic_count\n' + ''.join(f'{g[1]}\t{sample}\t{20+i*11}\n' for i, g in enumerate(GENES)),
        'vcf': f'##fileformat=VCFv4.2\n##source=SYNTHETIC_TEST_DATA\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n',
        'csv': 'sample_id,synthetic_cell_type,synthetic_count\n' + ''.join(f'{sample},{label},{10+i*3}\n' for i, label in enumerate(['Plasma','T','B','Myeloid'])),
    }
    return text[extension].encode()


def variant_templates(symbol, gid, chrom, start):
    # All offsets and amino-acid annotations below are invented, not clinical hotspots.
    kinds = [('M', 'missense_variant', 'A', 'T'), ('M', 'missense_variant', 'A', 'G'),
             ('N', 'stop_gained', 'A', 'T'), ('P', 'splice_region_variant', 'A', 'C'),
             ('F', 'frameshift_variant', 'A', 'AT'), ('D', 'inframe_deletion', 'AAAA', 'A'),
             ('I', 'inframe_insertion', 'A', 'ATTT'), ('S', 'synonymous_variant', 'A', 'G')]
    result = []
    for index, (kind, consequence, ref, alt) in enumerate(kinds):
        offset = [61, 142, 379, 712, 925, 1183, 1534, 1798][index]
        aa = offset // 3 + 1
        name = {'M': f'p.A{aa}T', 'N': f'p.A{aa}*', 'P': f'c.{offset}+2A>C',
                'F': f'p.A{aa}fs', 'D': f'p.A{aa}del', 'I': f'p.A{aa}insF', 'S': f'p.A{aa}='}[kind]
        result.append({'ssm_id': f'SYNTH-SSM-{symbol}-{index+1:02d}', 'gene_id': gid, 'symbol': symbol,
                       'chr': chrom, 'pos': start + offset, 'ref': ref, 'alt': alt,
                       'class': kind, 'consequence': consequence, 'mname': name})
    return result


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


def cgs_fixture(rng):
    """Random demonstration markers, with mutually consistent CGS facet labels.

    This is a fixture vocabulary, not a classifier for genomic/clinical input.
    These assignments do not control variants, survival, or treatment response.
    """
    # Arbitrary fixture weights keep High risk a minority, not an estimate of
    # clinical prevalence. Categories still follow the assigned criteria.
    del17p, tp53, gain1q = (rng.random() < probability for probability in (.05, .05, .2))
    igh = rng.choices((None, 't(4;14)', 't(14;16)', 't(14;20)'), weights=(70, 10, 10, 10))[0]
    del1p = rng.choices(('Absent', 'Monoallelic', 'Biallelic'), weights=(85, 13, 2))[0]
    high_b2m, normal_creatinine = rng.random() < .1, rng.random() < .7
    positive = (
        del17p or tp53,
        igh is not None and (gain1q or del1p != 'Absent'),
        (del1p == 'Monoallelic' and gain1q) or del1p == 'Biallelic',
        high_b2m and normal_creatinine,
    )
    markers = (
        ('del(17p) at qualifying clonal fraction', del17p),
        ('TP53 mutation', tp53),
        ('1q gain/amplification', gain1q),
        ('Monoallelic del(1p32)', del1p == 'Monoallelic'),
        ('Biallelic del(1p32)', del1p == 'Biallelic'),
        ('Beta-2 microglobulin >=5.5 mg/L', high_b2m),
        ('Creatinine <1.2 mg/dL', normal_creatinine),
        *((name, igh == name) for name in ('t(4;14)', 't(14;16)', 't(14;20)')),
    )
    return {
        'cgs_risk_category': 'High risk' if any(positive) else 'Standard risk',
        'cgs_risk_criteria': [label for label, present in zip(CGS_CRITERIA, positive) if present],
        'other_criteria': [f'{label}: {"Present" if present else "Absent"}' for label, present in markers],
    }


def generate(out, count=1000, seed=42):
    if not 10 <= count <= 1000:
        raise ValueError("Choose between 10 and 1000 synthetic cases")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    labels_rng = random.Random(seed + 1973)
    records, files, variants = [], [], []
    for number in range(1, count + 1):
        cid = f"SYNTH-CASE-{number:04d}"
        sid = f"SYNTH-SAMPLE-{number:04d}"
        age = rng.randint(40, 85)
        days = rng.randint(180, 3500)
        vital = rng.choice(["Alive", "Alive", "Dead"])
        regimen_short, regimen_name = labels_rng.choice(REGIMENS)
        project_id = 'SYNTHETIC-MM' if number <= (count + 1) // 2 else 'SYNTHETIC-RNA'
        resource = '/programs/SYNTHETIC/projects/' + ('MM' if project_id == 'SYNTHETIC-MM' else 'RNA')
        project = {"project_id": project_id, "name": "Synthetic discovery" if project_id == 'SYNTHETIC-MM' else 'Synthetic validation',
                   "program": {"name": "SYNTHETIC", "program_id": "SYNTHETIC", "dbgap_accession_number": ""},
                   "primary_site": ["Bone Marrow"], "disease_type": ["Multiple Myeloma"], "dbgap_accession_number": "",
                   "intended_release_date": "2026-01-01", "releasable": True, "released": True, "state": "released"}
        sample = {"sample_id": sid, "submitter_id": sid, "sample_type": "Primary Tumor", "tissue_type": "Tumor",
                  "tumor_descriptor": "Primary", "specimen_type": "Bone Marrow", "preservation_method": "Frozen"}
        case = {"id": cid, "case_id": cid, "submitter_id": cid, "project_id": project_id, "project": project,
                "batch_id": "SYNTHETIC", "primary_site": "Bone Marrow", "disease_type": "Multiple Myeloma",
                "index_date": "Diagnosis", "gender": ["female", "male"][(number - 1) % 2],
                "race": ["white", "black or african american", "asian"][((number - 1) // 2) % 3],
                "ethnicity": ["hispanic or latino", "not hispanic or latino"][((number - 1) // 6) % 2], "age_at_index": age,
                "age_at_diagnosis": age * 365, "days_to_birth": -age * 365, "vital_status": vital,
                "days_to_death": days if vital == "Dead" else None, "days_to_last_follow_up": days,
                "primary_diagnosis": "Multiple myeloma", "therapeutic_agents": regimen_name,
                "auth_resource_path": resource, "authz": [resource],
                "samples": [sample], "sample_id": sid, "sample_ids": [sid], "synthetic": True}
        case["demographic"] = {k: case[k] for k in ["gender", "race", "ethnicity", "vital_status", "days_to_birth", "days_to_death"]}
        case["diagnoses"] = [{"age_at_diagnosis": age, "days_to_last_follow_up": days,
                               "primary_diagnosis": case["primary_diagnosis"], "treatments": [{"therapeutic_agents": case["therapeutic_agents"]}]}]
        line = labels_rng.randint(1, 4)
        case['administered_regimen_lines'] = [{'line': line, 'first_line': 'Yes' if line == 1 else 'No',
                                              'regimen_name': regimen_name, 'regimen_short_name': regimen_short}]
        case['cgs_risk_key_criteria'] = cgs_fixture(labels_rng)
        for path, spec in COHORT_FIELDS.items():
            # Existing case/sample/project fields keep their values. Every other
            # categorical field has an explicit vocabulary; no generic fallback.
            if path.startswith('cgs_risk_key_criteria.'):
                continue
            if 'values' in spec:
                value = labels_rng.choice(spec['values'])
            elif spec['type'] in ('numeric_range', 'days'):
                value = rng.randint(1, 20)
            elif spec['type'].startswith('age'):
                value = age * 365
            elif spec['type'] == 'year':
                value = 2020 + number % 5
            else:
                raise ValueError(f'Missing fixture vocabulary: {path}')
            fill_field(case, path, value)
        case['outcomes'] = {'censor_os': int(vital == 'Dead'), 'censor_pfs': int(vital == 'Dead'),
                            'surivival_time_os': days, 'survival_time_pfs': days}
        records.append(case)
        sequence = "".join(rng.choice("ACGT") for _ in range(100))
        extension, file_format, strategy, category, data_type, workflow = FILE_PROFILES[((number - 1) // 12) % len(FILE_PROFILES)]
        filename = f"{sid}.synthetic.{extension}"
        payload = file_payload(extension, sid, sequence)
        (out / filename).write_bytes(payload)
        fid = f"SYNTH-FILE-{number:04d}"
        files.append({"id": fid, "file_id": fid, "file_name": filename, "file_size": len(payload),
                      "md5sum": hashlib.md5(payload, usedforsecurity=False).hexdigest(),
                      "data_category": category, "data_type": data_type, "data_format": file_format,
                      "experimental_strategy": strategy, "wgs_coverage": "30x", "platform": "Synthetic sequencer",
                      "submitter_id": fid, "type": "synthetic_test_file", "tags": ["synthetic"],
                      "created_datetime": "2026-01-01T00:00:00Z", "updated_datetime": "2026-01-01T00:00:00Z",
                      "center": {"short_name": "SYNTHETIC"}, "archive": {"archive_id": "SYNTH-ARCHIVE", "submitter_id": "SYNTH-ARCHIVE", "revision": 1},
                      "associated_entities": [{"entity_id": cid, "entity_type": "case", "case_id": cid}],
                      "analysis": {"analysis_id": f"SYNTH-ANALYSIS-{number:04d}", "workflow_type": workflow,
                                   "updated_datetime": "2026-01-01T00:00:00Z", "input_files": [], "metadata": {"read_groups": []}},
                      "index_files": [], "downstream_analyses": [{"workflow_type": workflow, "output_files": []}],
                      "access": "open", "state": "released", "acl": [project_id], "project_id": project_id,
                      "auth_resource_path": case["auth_resource_path"], "cases": [case], "synthetic": True})
    mutation_rng = random.Random(seed + 7391)
    for gene_index, (symbol, gid, chrom, start) in enumerate(GENES):
        templates = variant_templates(symbol, gid, chrom, start)
        for number, case in enumerate(records, 1):
            # Artificial differences by project, not inferred biological/demographic associations.
            probability = 0.60 if gene_index == 0 else 0.42 + 0.08 * (case['project_id'] == 'SYNTHETIC-RNA')
            if mutation_rng.random() < probability:
                weights = [55, 21, 6, 5, 4, 3, 3, 3] if case['project_id'] == 'SYNTHETIC-MM' else [36, 40, 6, 5, 4, 3, 3, 3]
                variant = mutation_rng.choices(templates, weights=weights, k=1)[0]
                variants.append({**variant, "case_id": case["case_id"], "sample_id": case["sample_id"], "sample": number})
    for case, file in zip(records, files):
        case['files'] = [{key: value for key, value in file.items() if key != 'cases'}]
    write_json(out / "cases.json", records)
    write_json(out / "files.json", files)
    write_json(out / "variants.json", variants)
    write_json(out / "provenance.json", {"synthetic": True, "generator_version": 4, "seed": seed,
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
                    sequence[variant['pos'] - 1:variant['pos'] - 1 + len(variant['ref'])] = list(variant['ref'])
            sequence = ''.join(sequence)
            for start in range(0, len(sequence), 80):
                fasta.write(sequence[start:start + 80] + '\n')
            fai.write(f'{chrom}\t100000\t{offset}\t80\t81\n')
    with (out / 'bulk-umap.tsv').open('w') as scatter:
        scatter.write('sample\tlabel\tx\ty\n')
        for index, case in enumerate(records):
            # Artificial islands make zoom/selection useful; they encode no clinical relationship.
            x, y = rng.gauss(index % 3 * 4, 1), rng.gauss(index % 2 * 4, 1)
            scatter.write(f"{case['sample_id']}\tSynthetic\t{x:.4f}\t{y:.4f}\n")
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
        if symbol == 'MYC':
            for alias in ('c-Myc', 'ENST00000621592', 'NM_002467', 'NM_002467.1'):
                db.execute("INSERT INTO genealias VALUES (?,?)", (alias, symbol))
            db.execute("INSERT INTO refseq2ensembl VALUES (?,?)", (gid, 'NM_002467'))
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
        groups = defaultdict(list)
        for variant in variants:
            groups[variant['ssm_id']].append(variant)
        for group in sorted(groups.values(), key=lambda group: (group[0]['chr'], group[0]['pos'])):
            var = group[0]
            impact = 'HIGH' if var['class'] in ('F', 'N') else 'MODERATE'
            csq = f"{var['alt']}|{var['consequence']}|{impact}|{var['symbol']}|{var['gene_id']}|Transcript|{var['gene_id']}|protein_coding|1|||{var['mname']}"
            carriers = {variant['sample_id'] for variant in group}
            genotypes = ['0/1' if c['sample_id'] in carriers else './.' for c in cases]
            handle.write(f"{var['chr']}\t{var['pos']}\t{var['ssm_id']}\t{var['ref']}\t{var['alt']}\t100\tPASS\tCSQ={csq}\tGT\t" + '\t'.join(genotypes) + '\n')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="generated")
    parser.add_argument("--cases", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    generate(args.out, args.cases, args.seed)
