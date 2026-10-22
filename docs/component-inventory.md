# Component inventory

Repository visibility and license metadata were checked through GitHub on
2026-10-21. Public visibility is distinct from an open-source license.

| Component | Visibility / license | Sandbox treatment |
| --- | --- | --- |
| `theMMRF/mmrf-data-commons` | Public, Apache-2.0 | Fetch pinned public source; optional synthetic presentation mode; replace historical fixture values in image build. |
| `@sjcrh/proteinpaint-client` | Published public package; ProteinPaint academic-use terms | Use the existing frontend dependency; no private client fork is referenced by its package lock. |
| `stjude/proteinpaint` and public `ppserver` | Public source/image, academic-use license | Use published server 2.216.0 on a pinned public base image, with a version-checked native scatter-filter correction. |
| `theMMRF/ppmmrf` | Private, no repository license reported | Exclude entirely. Write a fresh native Mds3 configuration against public contracts. |
| `theMMRF/guppy` | Public, Apache-2.0 repository license | Pin MMRF's `mmrf/version_0.1.0` branch commit, rather than the generic default branch. |
| `theMMRF/gen3-analysis` | Public, Apache-2.0 | Fetch pinned public source; use its real authenticated API and synthetic index configuration. |
| `theMMRF/mmrf_gen3` | Private | Do not distribute its Terraform state, plans, configuration, values, or history. Fresh sandbox Terraform and Helm live here. |
| `theMMRF/elasticsearch` | Private | Use the public Elastic 7.17.29 image with a fresh synthetic index. |
| `theMMRF/mmrf-users`, `aws-infra-utils`, `vlab-infra-utils`, `LZA_config`, `GenAI-Chatbot` | Private | Not required by this standalone sandbox and excluded. |
| `mmrf-esbuild`, `mmrf-mutation-indexer`, `mmrfdatamodel2`, `dictionaryutils`, `plaster`, `mmrf_dictionary`, `gen3-frontend-framework`, Gen3 SDK | Public | Public supporting projects; not required for runtime fixture generation. |
| `theMMRF/mmrf-models` | Public, no GitHub license metadata reported | Public visibility alone does not establish reuse permission; not imported into this project. |

The frontend package lock resolves `@sjcrh/proteinpaint-client` from the public npm
registry. The private MMRF customizations inspected are server-side dataset/API
adapters and deployment configuration. This establishes what this frontend source
build uses; it is not a claim about the provenance of every image currently
running in an environment that has not been inspected.

The private GitOps repository references custom service images and storage/auth
configuration. Merely cloning the public frontend would not reproduce that stack.
This sandbox replaces those deployment dependencies while retaining the actual
public frontend, Guppy, and analysis services.

Public reference:
[ProteinPaint source and license](https://github.com/stjude/proteinpaint),
[MMRF frontend](https://github.com/theMMRF/mmrf-data-commons),
[MMRF Guppy](https://github.com/theMMRF/guppy),
[MMRF analysis](https://github.com/theMMRF/gen3-analysis).

The sandbox applies `scripts/patch_proteinpaint.mjs` to the pinned public server
bundle because native prebuilt UMAPs otherwise ignore cohort filters when no
color/shape term is selected. The small correction applies the server's native
SQL filter before reading plotted samples. It is tested for selected and empty
cohorts, fails the build on an unexpected version/implementation, and retains the
upstream license. It contains no private adapter code. The curated chart menu,
combined single-cell layout, and scatter presentation options are freshly
configured through the public dataset contract, with generated local file paths.
