"""Seed an isolated Elasticsearch instance with generated fixtures only."""
import json
import os
import hashlib
from pathlib import Path
import time
import urllib.error
import urllib.request

base = os.environ.get("GEN3_ES_ENDPOINT", "http://elasticsearch:9200").rstrip("/")
if base not in ("http://elasticsearch:9200", "http://127.0.0.1:19200"):
    raise SystemExit("Seeder only supports the isolated sandbox Elasticsearch address")
root = Path(os.environ.get("DATA_DIR", "/data"))


def request(path, data=None, method="GET", content_type="application/json"):
    raw = data.encode() if isinstance(data, str) else json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(base + path, data=raw, method=method, headers={"Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise RuntimeError(exc.read().decode()) from exc
        raise


def mapping(value):
    if isinstance(value, list):
        return mapping(next((v for v in value if v is not None), ""))
    if isinstance(value, dict):
        return {"type": "nested", "properties": {k: mapping(v) for k, v in value.items()}}
    if isinstance(value, bool):
        return {"type": "keyword"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "double"}
    return {"type": "keyword"}


def merge(left, right):
    for key, value in right.items():
        if key not in left:
            left[key] = value
        elif isinstance(value, dict) and isinstance(left[key], dict):
            merge(left[key], value)
    return left


def normalize_types(props):
    for key, value in props.items():
        if "properties" in value:
            normalize_types(value["properties"])
        if key in ('project', 'transcript', 'annotation') and 'properties' in value:
            value['type'] = 'object'
        elif key.startswith("days_to_") or key in ("age_at_diagnosis", "age_at_index", "file_size", "start_position", "end_position", "case_count", "file_count"):
            props[key] = {"type": "integer"}


def arrays(doc, prefix=""):
    result = set()
    if isinstance(doc, dict):
        for key, value in doc.items():
            name = f"{prefix}.{key}" if prefix else key
            if isinstance(value, list):
                result.add(name)
                for item in value:
                    result.update(arrays(item, name))
            elif isinstance(value, dict):
                result.update(arrays(value, name))
    return result


if __name__ == "__main__":
    for attempt in range(60):
        try:
            request("/_cluster/health?wait_for_status=yellow&timeout=2s")
            break
        except (OSError, urllib.error.URLError):
            time.sleep(2)
    cases = json.loads((root / "cases.json").read_text())
    files = json.loads((root / "files.json").read_text())
    variants = json.loads((root / "variants.json").read_text())
    if any(not c.get("synthetic") or not c["case_id"].startswith("SYNTH-CASE-") for c in cases):
        raise SystemExit("Refusing non-synthetic fixtures")
    # Refuse a stale index rather than silently mixing different generated cohorts.
    fingerprint = hashlib.sha256(b''.join((root / f).read_bytes() for f in ('cases.json', 'files.json', 'variants.json'))).hexdigest()
    try:
        previous = request('/sandbox_seed_complete/_doc/ready')['_source']
        if previous.get('fingerprint') != fingerprint:
            raise SystemExit('Fixtures changed: discard the disposable search volume before reseeding')
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    by_id = {c["case_id"]: c for c in cases}
    for case, file in zip(cases, files):
        case["files"] = [{k: v for k, v in file.items() if k != "cases"}]
        case["summary"] = {"file_count": 1, "data_categories": [{"file_count": 1, "data_category": "Sequencing Reads"}],
                           "experimental_strategies": [{"experimental_strategy": "WGS", "file_count": 1}]}
    for case in cases:
        case['available_variation_data'] = ['ssm', 'cnv']
        case['gene'] = []
    occurrences = []
    for number, v in enumerate(variants):
        gene = {"gene_id": v["gene_id"], "symbol": v["symbol"], "name": "Synthetic " + v["symbol"], "biotype": "protein_coding", "is_cancer_gene_census": False}
        mutation = {"ssm_id": f"SYNTH-SSM-{number:04d}", "chromosome": v["chr"], "start_position": v["pos"],
                    "end_position": v["pos"], "reference_allele": v["ref"], "tumor_allele": v["alt"],
                    "mutation_type": "Simple Somatic Mutation", "genomic_dna_change": f"{v['chr']}:g.{v['pos']}A>T"}
        mutation['observation'] = [{'observation_id': f'SYNTH-OBS-{number:04d}', 'sample': {'sample_id': v['sample_id']}}]
        mutation['consequence'] = [{'consequence_type': 'missense_variant', 'transcript': {'is_canonical': 'true', 'consequence_type': 'missense_variant', 'aa_change': v['mname'], 'annotation': {'vep_impact': 'MODERATE'}, 'gene': gene}}]
        by_id[v['case_id']]['gene'].append({**gene, 'ssm': [mutation]})
        occurrence = {"ssm_occurrence_id": f"SYNTH-OCC-{number:04d}", "case": by_id[v["case_id"]],
                      "sample": {"sample_id": v["sample_id"]}, "ssm": mutation}
        occurrences.append({"id": occurrence["ssm_occurrence_id"], "ssm_occurrence_id": occurrence["ssm_occurrence_id"],
                            **mutation, "gene": gene, "ssm": mutation, "occurrence": [occurrence],
                            "case": by_id[v["case_id"]], "consequence": mutation["consequence"],
                            "auth_resource_path": "/programs/SYNTHETIC/projects/MM"})
    genes = []
    for symbol in sorted({v["symbol"] for v in variants}):
        selected = [o for o in occurrences if o["gene"]["symbol"] == symbol]
        gene = selected[0]["gene"]
        genes.append({**gene, "id": gene["gene_id"], "ssm": [{"ssm_id": o["ssm"]["ssm_id"], "occurrence": [o["occurrence"]]} for o in selected],
                      "case": [{k: value for k, value in o["case"].items() if k != 'gene'} | {'ssm': [o['ssm']], 'cnv': [{'cnv_change_5_category': 'Gain'}]} for o in selected], "auth_resource_path": "/programs/SYNTHETIC/projects/MM"})
    # A mutation-centric document is keyed by the mutation ID, while its separate
    # occurrence-centric counterpart retains the observation ID.
    mutations = [{**o, 'id': o['ssm_id']} for o in occurrences]
    documents = {
        "case": cases, "case_centric": cases, "file": files,
        "project": [{**cases[0]["project"], "id": "SYNTHETIC-MM", "case_count": len(cases), "file_count": len(files), "auth_resource_path": "/programs/SYNTHETIC/projects/MM"}],
        "gene_centric": genes, "ssm_centric": mutations, "ssm_occurrence_centric": occurrences,
        "cnv_centric": [{"id": "SYNTH-CNV-0001", "cnv_id": "SYNTH-CNV-0001", "gene": {k: genes[0][k] for k in ('gene_id', 'symbol')}, "cnv": {"cnv_change": "Gain"}, "case": cases[0]}],
        "cnv_occurrence_centric": [{"id": "SYNTH-CNV-OCC-0001", "cnv_occurrence_id": "SYNTH-CNV-OCC-0001", "gene": {k: genes[0][k] for k in ('gene_id', 'symbol')}, "cnv": {"cnv_change": "Gain"}, "case": cases[0]}],
    }
    config = {"indices": [], "auth_filter_field": "auth_resource_path", "arrayConfig": []}
    for kind, docs in documents.items():
        props = {}
        array_fields = set()
        for doc in docs:
            merge(props, mapping(doc)["properties"])
            array_fields.update(arrays(doc))
        normalize_types(props)
        if kind == 'gene_centric':
            props['case']['properties']['project']['type'] = 'object'
        if kind in ('ssm_centric', 'ssm_occurrence_centric'):
            props['consequence']['properties']['transcript']['type'] = 'object'
            props['consequence']['properties']['transcript']['properties']['annotation']['type'] = 'object'
            props['occurrence']['properties']['case']['type'] = 'object'
            props['occurrence']['properties']['case']['properties']['project']['type'] = 'object'
        index = f"sandbox_{kind}"
        try:
            request(f"/{index}")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            request(f"/{index}", {"settings": {"number_of_shards": 1, "number_of_replicas": 0, "mapping.nested_fields.limit": 200}, "mappings": {"properties": props}}, "PUT")
        bulk = "".join(json.dumps({"index": {"_index": index, "_id": d["id"]}}) + "\n" + json.dumps(d) + "\n" for d in docs)
        result = request("/_bulk?refresh=true", bulk, "POST", "application/x-ndjson")
        if result.get("errors"):
            raise RuntimeError(json.dumps(result))
        config["indices"].append({"index": index, "type": kind})
        config["arrayConfig"].append({"index": index, "array": sorted(array_fields)})
        print(f"Seeded {len(docs)} synthetic {kind} records", flush=True)
    (root / "guppy.json").write_text(json.dumps(config, indent=2) + "\n")
    try:
        request('/sandbox_seed_complete')
    except urllib.error.HTTPError:
        request('/sandbox_seed_complete', {}, 'PUT')
    request('/sandbox_seed_complete/_doc/ready?refresh=true', {'synthetic': True, 'fingerprint': fingerprint}, 'PUT')
