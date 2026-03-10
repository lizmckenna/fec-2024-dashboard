# 2024 FEC Campaign Tech & Digital Spending Dashboard

Interactive dashboard analyzing how federal campaigns spent money on technology vendors, digital advertising platforms, and campaign infrastructure during the 2024 election cycle.

## Live Dashboard

**[View the live dashboard on GitHub Pages](https://elizabethmck.github.io/fec-2024-dashboard/)**

## What's Inside

### Dashboard (`index.html`)
A single-page interactive dashboard with 6 tabs:

- **Overview** — KPIs, top providers by spending, category breakdowns, party split
- **All Providers** — Sortable table of all 20 tracked vendors with D/R split bars
- **D vs R** — Head-to-head comparison across fundraising, CRM, SMS, consulting, and ad platforms
- **By Candidate** — Which candidates spent how much with which vendors (Trump, Harris, Biden, DNC, etc.)
- **Digital Ads** — Platform-level ad spending (Meta, Google, Snap, X) plus media buying intermediaries
- **Data Coverage** — Methodology, what's included/missing, and why Republican CRM data looks different

### Data Files (`data/`)

| File | Description |
|------|-------------|
| `fec_2024_all_providers.csv` | All 20 vendors with totals, D/R splits, sources |
| `fec_2024_candidate_by_vendor.csv` | 76 candidates/entities with per-vendor spending |
| `fec_2024_committee_by_vendor.csv` | 96 committees with per-vendor spending |
| `fec_2024_tech_disbursements_detail.csv` | 503 raw committee-level payment records |
| `fec_2024_party_tech_spending.csv` | Records organized by provider and party |
| `fec_2024_complete_provider_summary.csv` | 13-provider summary (earlier version) |
| `fec_2024_tech_provider_summary.csv` | 6-provider summary (API-only data) |
| `fec_full_extractor.py` | Python script for full extraction with your own API key |

## Key Findings

- **$2.08B** total tracked across 20 vendors
- **WinRed** ($311M) slightly edges **ActBlue** ($297M) in fundraising platforms
- **Waterfront Strategies** ($858M) is the single largest vendor — a D-aligned media buyer
- Democrats outspend Republicans 3:1 on digital ads (Meta + Google)
- **NGP VAN** ($79M) has no single Republican equivalent — GOP distributes across Data Trust ($7M) + i360 ($4.3M) + Campaign Sidekick
- Trump accounts for 99.4% of all WinRed spending

## Data Sources

- **FEC OpenFEC API** — Direct schedule B disbursement queries (6 fundraising/CRM platforms)
- **OpenSecrets** — Vendor profiles with FEC-reported payments (14 additional vendors)
- **Brennan Center / Wesleyan Media Project** — Platform-reported ad transparency data
- **Center for Campaign Innovation** — 2024 post-election GOP technology survey

## Run Your Own Analysis

Get a free API key at [api.data.gov/signup](https://api.data.gov/signup/) and run:

```bash
python data/fec_full_extractor.py
```

This will query the full FEC database for 70+ tech provider names across 10 categories.

## License

Data is sourced from public FEC filings and public reports. This project is for educational and research purposes.
