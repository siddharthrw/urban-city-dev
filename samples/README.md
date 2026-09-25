# Sample files: made-up test data

**Nothing in this folder is real data.** The files exist to try the data inbox and to test it.
Their names start with `SAMPLE_`, so the app labels everything imported from them as
"SAMPLE: made-up test data".

| File | Import as | What it exercises |
|---|---|---|
| `SAMPLE_traffic_counts.csv` | Traffic counts | Title rows above the header; road names with abbreviations (`Rd`, `Dr.`) and a typo (`Nrth`); a name shared by many streets (`1st Street`, `Anna Salai`); a road that doesn't exist; a bad number (`abc`); one row placed by latitude/longitude |
| `SAMPLE_bus_stops.kml` | Bus stops | KML points with attributes; one point in the sea that must not link to a road |
| `SAMPLE_width_survey.csv` | Road width surveys | A surveyed width (`24.5 m`) that upgrades Cathedral Road to **verified**. Delete the import afterwards so no made-up width stays on the map. |
| `SAMPLE_standards_excerpt.pdf` | Rules > Documents | A made-up 4-page standard: ingest, embed, AI-extract 5 rules with quotes and pages, approve/reject (`build_sample_standards_pdf.py` regenerates it) |
| `SAMPLE_expert_rules.csv` | Rules > Expert sheet | The If/Then/Because table from the plan; imports 4 expert rules. Delete `rules/active/expert_*.yaml` afterwards if you don't want them committed. |

To try them, open **Data inbox** in the app, choose the layer type, and upload the file.
