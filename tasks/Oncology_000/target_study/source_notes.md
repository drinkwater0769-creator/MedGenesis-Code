# Source Notes: Oncology_000

## Bound Literature

- PMID: 25079552
- Title: Comprehensive molecular profiling of lung adenocarcinoma
- Journal/date: Nature (2014 Jul 31)
- DOI: 10.1038/nature13385
- PubMed: https://pubmed.ncbi.nlm.nih.gov/25079552/

## Data Source

- Dataset: TCGA/GDC
- Access: open
- URL: https://portal.gdc.cancer.gov/
- Description: NCI Genomic Data Commons / TCGA-LUAD clinical case metadata plus open masked WXS somatic mutation MAF files.

## Reproduction Target

Reconstruct the TCGA-LUAD molecular-profile workflow using official GDC open data. The bundled reference run downloads clinical cases, the GDC masked somatic mutation file index, and per-aliquot MAF files; derives patient-level non-silent driver mutation indicators; and locks metrics for LUAD cohort size, sequenced denominator, TP53/KRAS/EGFR/STK11/KEAP1 alteration rates, and EGFR/KRAS near-mutual-exclusion.

## Primary Endpoint

molecular subtype and survival availability in lung adenocarcinoma

## New-Discovery Extension

After reproducing core driver alteration patterns, test one conservative extension: a compact EGFR/KRAS exclusivity signal, subgroup check, sensitivity analysis, or deployment-risk analysis that remains within the open GDC source data's support.

## Leakage and Licensing

The benchmark may cite the paper and PubMed metadata, but it must not redistribute copyrighted full text, non-public source tables, or controlled patient-level records. For public release, provide extraction code and provenance; for controlled data, provide execution instructions and scoring targets in a governed environment.
