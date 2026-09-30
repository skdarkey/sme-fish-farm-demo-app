# Pondwise â€” fish farm management & analytics

A runnable first version using Streamlit, SQLAlchemy 2, PostgreSQL and Plotly.
Includes pond and stocking registers, daily records, record corrections, feed and
growth trends, water alerts, harvest tracking, historical KPIs and CSV exports.
Also includes native OIDC sign-in, manager/stocktaker roles, pond water visits,
advanced trends and a configurable farm-data LLM chatbot.

## Run locally

Requires Python 3.11+.
`requirements-lock.txt` records the exact packages validated in the Windows Python
3.12 development environment; use it instead of `requirements.txt` for that setup.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open http://localhost:8501. Default storage uses `data/demo.db` (SQLite), but
authentication now defaults to secure OIDC and requires provider configuration.
Follow [authentication setup](docs/AUTHENTICATION.md). For a local synthetic-data
preview only, set `APP_MODE=demo` and `AUTH_MODE=demo` in `.env` before starting.
On Windows, `./run.ps1` starts the installed app, bound to localhost.
Use `./run.ps1 -Demo` to explicitly select local SQLite and demo access for that
process, even if the terminal inherits hosted settings. Stop old Streamlit
processes before switching modes.
Click **Load sample farm** to create three ponds and 60 days of synthetic records,
or start with your own empty register. Demo data is never seeded automatically.

## Connect PostgreSQL

1. Copy `.env.example` to `.env`.
2. Set a private `POSTGRES_PASSWORD` and the matching password in `DATABASE_URL`.
   URL-encode special characters in the connection URL password.
3. Set `APP_MODE=postgres`.
4. Start the database with `docker compose up -d db`, or point the URL at an
   existing PostgreSQL database.
5. Start/restart Streamlit. Tables are created in the selected database.

The Docker database binds to localhost and stores records in a persistent volume.
No demo records are inserted into PostgreSQL. Mode switching selects a separate
database; it does not migrate demo data. Never commit `.env` or database files.
Environment variables take precedence over `.env`.

## Client branding

Set `CLIENT_NAME=Sekom Farms` in `.env` (or the hosting environment) and restart
Streamlit. The sidebar and browser title become **A3 Pondwise | Sekom Farms**.
Leaving it blank displays **A3 Pondwise**. Use a separate database and credentials
for each client deployment; this display name does not isolate client data.

## Architecture

```text
Streamlit UI (app.py)
    â”œâ”€â”€ Business services (farm/services.py): validated transactional writes
    â”‚       â””â”€â”€ SQLAlchemy models â†’ PostgreSQL
    â””â”€â”€ Analytics (farm/analytics.py): derived KPIs and alerts
            â””â”€â”€ Plotly charts / CSV reports / scripts/report.py
```

The four responsibilities remain separate even though Streamlit hosts both the UI
and backend logic. There is no separate HTTP API in this version. Services and
analytics can be reused by an API or scheduled pipeline later.

| Entity | Purpose |
| --- | --- |
| Pond | Named production unit, area and average depth |
| Batch | Species, stocking date, initial fish count and average weight |
| DailyLog | One record per batch/date: feed, mortality, harvest, growth, water and notes |
| WaterVisit | Multiple pond observations per day, water chemistry and corrective follow-up |
| AppUser / AccessAudit | OIDC identities, approved roles, disabled status and access-change history |

Multiple batches can share a pond. Daily-log water readings remain tied to batches;
the dedicated Water visits page records pond observations independently. These two
sources remain separate in Advanced insights to avoid double counting. Overview
alerts currently use daily-log readings; water-visit analysis is on Advanced insights.
Fish transfers and restocking an existing batch are not supported;
register a new batch for a new stocking cycle. A batch becomes depleted when its
remaining fish count reaches zero.

## Metric definitions

- Remaining fish = stocked âˆ’ deaths âˆ’ harvested count.
- Survival = (stocked âˆ’ deaths) / stocked Ã— 100; harvest is not mortality.
- Estimated standing biomass = remaining fish Ã— latest sample weight / 1,000.
  Until a growth sample exists, this uses stocking weight. Sample dates are shown.
- Economic FCR = cumulative feed through the latest growth sample / (standing
  biomass at that sample + cumulative harvested kilograms âˆ’ initial biomass).
  Feed and movements after that sample do not enter FCR. FCR is blank without a
  growth sample or positive net gain. Mortality biomass is not recovered.
- Dashboard metrics are cumulative as of the selected date. Trend start only
  filters charts and daily-record exports.
- Water alerts evaluate the latest nonmissing oxygen and pH readings independently.
  Their dates are shown; absent/stale measurements do not mean safe conditions.
  The 4 mg/L oxygen and 6.5â€“8.5 pH defaults are illustrative, session-configurable
  thresholds, not species-specific husbandry recommendations.

Missing daily logs represent missing observations, not confirmed zero activity.
The app does not interpolate growth or make ML predictions.

## Validation and reporting

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.report --output reports/performance.csv
# Optional historical snapshot:
.\.venv\Scripts\python.exe -m scripts.report --as-of 2026-09-01
```

Run the report command from the project directory after initializing the database
with the app. The reporting script only reads farm data and writes the requested CSV.
The tests use isolated in-memory SQLite databases; they do not modify farm records.

## Scope and next steps

This is an internal MVP. Authentication and page/action roles are implemented;
live OIDC sign-in requires your provider credentials. The chatbot requires a model
server and model configuration. Immutable operational audit history,
automatic backups, schema migrations, feed inventory/cost accounting and external
alert delivery are not yet implemented. Replacing a daily record overwrites it;
an operational audit trail is needed before accountable multi-user operation.
User-access changes have a separate audit table. Configure OIDC and HTTPS before
deployment; never expose demo authentication publicly.

`create_all` bootstraps an empty schema; it does not migrate existing tables.
The retired demonstration research tables can be removed from an existing deployment
with `python -m scripts.remove_fwi_data`. This drops only `research_records` and
`research_datasets`, without CASCADE, and verifies other table row counts.
Existing ponds, batches, daily logs, water visits and access records are preserved.
Deletion does not erase historical backups, PostgreSQL WAL, or storage snapshots;
remove demonstration copies there under your backup retention policy.
Adopt Alembic before evolving a database containing real records. PostgreSQL row
locks serialize daily writes per batch; the SQLite demo is for local single-user
evaluation. The current dashboard reads all records and is designed for small
farm datasets; larger deployments should push filtering/aggregation into SQL.

## Feature guides

- [Authentication, registration and role administration](docs/AUTHENTICATION.md)
- [Advanced trends and LLM server configuration](docs/INSIGHTS.md)

Implementation references: [Streamlit data connections](https://docs.streamlit.io/develop/concepts/connections/connecting-to-data)
and [SQLAlchemy session basics](https://docs.sqlalchemy.org/en/20/orm/session_basics.html).
