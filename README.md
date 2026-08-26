# Job Application Tracker

A simple job application tracker (Flask + Postgres) modeled on the columns in
`Intern Apps.xlsx`. The web GUI is capture-first: paste a job link or upload a
screenshot, and it reads the posting (scrape / local OCR), infers the fields,
and prefills the form for you to validate instead of typing from scratch.

## Setup

1. Install the Tesseract OCR binary (needed for screenshot capture):

   ```bash
   brew install tesseract
   ```

2. Install Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a Postgres database and point `DATABASE_URL` at it. Defaults to
   `postgresql://localhost/jobtracker` if unset.

   ```bash
   createdb jobtracker
   export DATABASE_URL="postgresql://localhost/jobtracker"
   ```

   The `applications` table is created automatically on first run.

## Quick launch from Terminal

After one-time install (adds `~/bin` to your PATH):

```bash
./install-applied.sh
```

Open a new terminal tab and type:

```bash
applied
```

Paste a job link, and/or a screenshot:

- **Link:** paste the URL as usual.
- **Screenshot file:** drag a file into the terminal, or paste a path (`~/Desktop/...`;
  quotes are stripped).
- **Clipboard image:** Terminal cannot receive Cmd+V of a *photo*. Copy the
  screenshot (e.g. Cmd+Ctrl+Shift+4, or Copy in Preview), leave the link blank if
  you are not using one, then press **Enter** at
  `Screenshot path (or Enter to use clipboard image)` — the CLI reads the image
  from the macOS clipboard and OCRs it.

Fields are inferred (same scrape/OCR as the web GUI), you confirm/edit in the
terminal, and the row is saved — no browser. A link and a screenshot can both
be used; clipboard is only tried when there is no link and you press Enter on
the screenshot prompt.

## Run the web GUI

```bash
flask --app app run
```

Then open http://127.0.0.1:5000

- **Applications** list shows every row with status badges.
- **+ New Application** starts the capture-first flow:
  1. Paste a job link (scraped with BeautifulSoup) and/or upload a screenshot
     (OCR'd with Tesseract). Screenshots are saved under `uploads/`.
  2. Fields are inferred with format-aware heuristics (**Workday**, **Greenhouse**,
     **iCIMS** POC; otherwise generic regex) and prefilled — including
     posted date, application deadline, department, and US-citizen-required
     when visible. See [JD-FORMATS.md](JD-FORMATS.md).
  3. Validate/edit the form and save. The **application date defaults to today**
     (editable for backfilling older applications).
  - Prefer to type it all yourself? Use the "Skip — enter details manually" link.
- An application's detail page still lets you (re)capture the job description
  from a link or screenshot.

## Add via CLI (same as `applied`)

```bash
python cli.py
```

## Import existing spreadsheet data (optional)

Load the current rows from `Sheet1` of the spreadsheet:

```bash
python import_xlsx.py
```

## Notes

- JS-heavy job boards (Workday, Handshake) may return little text from plain
  link scraping; the screenshot + OCR path is the reliable fallback.
- Extracted job description text is stored raw (no LLM cleanup).
