# JD format extractors (Option A POC)

US-focused (San Diego / US remote). Prefill is best-effort — always validate.

## Supported now

| Format | Detect by | Extra pulls from URL |
|---|---|---|
| **Workday** | `*.myworkdayjobs.com` or Job Requisition chrome | req id after `_R…` / `_JR…`; company from tenant |
| **Greenhouse** | `greenhouse.io`, `gh_jid=`, or "Powered by Greenhouse" | `gh_jid` / `/jobs/{id}`; board slug → company |
| **iCIMS** | `*.icims.com` or "Powered by iCIMS" | `/jobs/{id}`; `careers-{slug}` → company |

Everything else uses the **generic** regex fallback.

## Fields inferred

`role`, `company`, `location`, `location_type`, `pay`, `job_id`,
`posted_date`, `application_deadline`, `department`, `us_citizen_required`.

- `application_deadline` = date on the JD  
- `due_date` = your expected-response date (manual)  
- `us_citizen_required` = true / false / unknown from citizenship wording

## Flow

1. Paste link and/or screenshot  
2. Scrape and/or OCR → raw JD text  
3. `detect_format(url, text)` → family extractor  
4. Prefill form / CLI prompts → you confirm → save  

Code: [`parse.py`](parse.py) (`detect_format`, `extract_fields`).

## Later

Handshake, LinkedIn, Lever, Ashby, Phenom, Radancy, Eightfold, etc.
