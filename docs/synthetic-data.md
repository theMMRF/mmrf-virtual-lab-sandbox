# Synthetic data

The default seed (`42`) creates 1,000 fabricated cases. Reusing the seed and
generator version reproduces the same records. No patient dataset is used.

## Demonstration scenarios

- **Survival:** High risk and KRAS-mutated groups have shorter simulated event
  times. Independent censoring produces overlapping curves rather than perfect
  separation. Effect sizes are arbitrary, not fitted clinical estimates.
- **Expression:** 36 genes share uneven latent groups and correlated variation.
  Sixteen genes also have an artificial KRAS-associated expression shift, giving
  differential expression a useful top-10 result. Count matrices derive from
  the same expression values; downloadable RNA-Seq TSVs match the count matrix.
- **Mutations:** Six genes have recurring public protein-change examples plus
  invented background variants. Carrier frequencies and hotspot weights are
  arbitrary. TP53 variants match the corresponding CGS marker.

The KRAS survival effect is a test scenario, not a claim that every KRAS mutation
predicts poor survival in myeloma. Expression signatures and background variant
annotations are also demonstration constructs.

## Reference annotations

`synthetic/public-proteins.json` records the UniProt accession, source URL, and
protein sequence for each expression gene. Sequences were retrieved on
2026-10-28. Attribution: **The UniProt Consortium**, [UniProt](https://www.uniprot.org/),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), per its
[data license](https://www.uniprot.org/help/license).

Reference proteins are retained unchanged. Coding DNA is a deterministic
back-translation; chromosome coordinates, single-exon models, and flanking DNA
are artificial. They are **not GRCh38 coordinates**, although the frontend uses
the `hg38` dataset key. Protein-change labels must not be interpreted as real
genomic HGVS annotations.

Public variant examples:

| Genes | Examples and source |
| --- | --- |
| KRAS, NRAS, BRAF | RAS codons 12, 13, 61 and BRAF V600/D594; [myeloma sequencing study](https://pmc.ncbi.nlm.nih.gov/articles/PMC6097138/) |
| TP53 | R175, Y220, R248, R273, R282; [TP53 hotspot study](https://pubmed.ncbi.nlm.nih.gov/41595714/) |
| DIS3 | S477R, G766R, R780K; [functional myeloma study](https://pubmed.ncbi.nlm.nih.gov/24150935/) |
| MYC | T58A and T58I; [lymphoma study](https://pmc.ncbi.nlm.nih.gov/articles/PMC8657136/) |

MYC coding examples come from lymphoma research, not common myeloma coding
hotspots. Its reference isoform is UniProt P01106-1, which uses the conventional
T58 numbering; KRAS uses the 188-amino-acid P01116-2 isoform.
