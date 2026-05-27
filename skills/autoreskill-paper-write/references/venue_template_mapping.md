# Venue Template Mapping

AutoResearch should treat the target venue as a profile, not as a hard-coded NMI path. NMI remains one supported journal profile.

Supported profile families:

| Profile | Type | Required package emphasis |
| --- | --- | --- |
| `unspecified_top_tier` | generic | target-venue summary, reproducibility checklist, venue checklist gaps |
| `NMI` | journal | broad-reader summary, significance statement, cover letter, reporting/admin gaps |
| `NeurIPS` | conference | reproducibility checklist, ethics/impact, supplementary readiness |
| `ICML` | conference | empirical protocol clarity, reproducibility checklist, limitations/ethics |
| `ICLR` | conference | open-review clarity, reproducibility evidence, limitations/ethics |
| `CVPR` / `ICCV` / `ECCV` | conference | visual benchmark fairness, dataset/license checks, supplementary readiness |
| `ACL` / `EMNLP` / `NAACL` | conference | limitations, ethics statement, dataset/annotation transparency |
| `TPAMI` | journal | cover letter, extended empirical evidence, reproducibility and data/code availability |
| `JMLR` | journal | archival clarity, complete appendices/proofs where relevant, data/code availability |

Common required artifacts:

- `paper/main.tex`
- `paper/main.pdf`
- `paper/VENUE_PROFILE.md`
- `paper/TARGET_VENUE_SUMMARY.md`
- `paper/VENUE_CHECKLIST_GAPS.md`
- `reviewer/CITATION_INTEGRITY_REPORT.md`

Venue-specific artifacts are declared in `submission_ready.json.required_artifacts`. `submission_lint.py` must read that list instead of assuming every target is NMI.
