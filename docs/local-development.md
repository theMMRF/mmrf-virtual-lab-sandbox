# Local development modes

The sandbox runs the same public frontend source, Guppy, Gen3 analysis, and
ProteinPaint server in separate containers. This repository supplies their
configuration, data, and launcher; it does not vendor them into a monorepo.
Elasticsearch is local too. A small synthetic identity gateway supplies the
Fence/Arborist contracts needed to use those services without real credentials.

| Mode | Launch and configuration | Data and identity |
| --- | --- | --- |
| Regular frontend testing | Your existing frontend checkout, startup command, and real-service configuration | Your usual authorized services and credentials; unchanged by this launcher |
| Synthetic sandbox | `scripts/start.sh` in this repository, then `http://localhost:3080` | Local containers, generated fixtures, disposable signing keys; no Gen3 credentials file |

The frontend's explicit `NEXT_PUBLIC_SYNTHETIC_SANDBOX=1` build flag controls the
banner, disables analytics, and prevents the historical demo-data mode. It does
not implement authentication or bypass production login. Setting that flag alone
on a regular frontend server does not create the synthetic backend. The gateway
provides the disposable session and routes all service requests locally.

The gateway accepts only its own service names or loopback as upstreams, replaces
incoming identity before forwarding, and strips login cookies from responses.
It does not save an `access_token` cookie that could replace a normal development
login on another localhost port. Browser storage is separate by origin, including
port. The Docker network and volume belong to this Compose project; no real
commons endpoints, credential mounts, or existing deployment resources are used.
This is a local developer environment, not an air-gapped or multi-tenant system.

For frontend changes, edit the disposable public `.sources/frontend` checkout,
then run `docker compose build frontend && docker compose up -d --wait frontend`.
Use Compose directly while editing: the source-fetch helper deliberately refuses
to overwrite a dirty checkout. Keep durable application changes in the frontend's
own repository/PR; pin the resulting public commit in `sources.json`. Your normal
frontend checkout and its environment files do not need to change.

## Suggested manual checks

Reload the page and clear cohort filters first: the full dataset should show
**1,000 cases**. Previously saved explicit-ID cohorts retain their original IDs.
With the default seed, male + white and female + black or African American each
select **167 cases**. Try those groups in Clinical Data Analysis, Cohort Comparison,
Mutation Frequency, OncoMatrix, and ProteinPaint. MYC and c-Myc both work; the
advertised Ensembl and RefSeq examples resolve to the same synthetic gene.

Correlation exposes **Correlation Input** and **Survival**. Bulk UMAP starts with
small points and no preselected clinical color/shape. A small version-checked
correction to the public server ensures that this uncolored view respects cohort
filters; it is documented in the component inventory. In Single Cell RNA-seq,
select **combined**, then **Meta analysis**; use Lineage Group, Subcluster, Sample,
Subcluster Compartment, Cell Type, or gene expression. The combined file contains
80 cells per synthetic case and is filtered to the selected cohort. Cell fractions
and pseudobulk mean/percent/total expression are derived from those same cells.

## Limits

- Clinical metadata is representative rather than complete, and CNV API indexes
  remain minimal fixtures. The tested flows focus on demographic cohorts, gene
  mutations/survival, expression, UMAP, and file search.
- Six fixture genes and fabricated short reference chromosomes support tool and
  API development. This is not whole-genome coverage or a biological model. Even
  plausible-looking associations and p-values have no scientific meaning.
- The original ten-case survival threshold remains. Very restrictive filters can
  still produce a small or empty group; that should remain visible to an agent.
- One shared synthetic identity replaces real login/permissions behavior. No
  uploads, notebooks, spatial assays, methylation, production storage access, or
  biomedical knowledge graph are provided. File downloads are fabricated FASTA.
- Public ProteinPaint retains its academic-use license. Its public image needs
  amd64 or Docker emulation. AWS acceptance remains an operator-controlled step.
