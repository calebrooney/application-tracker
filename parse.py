"""Local JD capture + field inference (Option A POC).

Grab text via parse_link (HTML scrape) or ocr_image (Tesseract).
detect_format picks workday / greenhouse / icims from URL or OCR chrome;
extract_fields runs a label-anchored extractor for that family, else generic
regex. Best-effort — user always validates before save.
"""

import re
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# Empty field dict returned when nothing is found.
EMPTY_FIELDS = {
    "role": None,
    "company": None,
    "location": None,
    "location_type": None,
    "pay": None,
    "job_id": None,
    "posted_date": None,
    "application_deadline": None,
    "department": None,
    "us_citizen_required": None,
}


def parse_link(url):
    """Fetch a URL and return visible text with page title prepended."""
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text("\n").splitlines()]
    body = "\n".join(line for line in lines if line)
    return f"{title}\n{body}" if title else body


def ocr_image(path):
    """Run Tesseract OCR on an image file and return the detected text."""
    import pytesseract
    from PIL import Image

    return pytesseract.image_to_string(Image.open(path)).strip()


def detect_format(url=None, text=None):
    """Return 'workday', 'greenhouse', 'icims', or 'generic' from URL/OCR chrome."""
    url = (url or "").lower()
    text = text or ""

    if "myworkdayjobs.com" in url or re.search(r"\bworkday\b", text, re.I):
        # Prefer URL; Workday word in body alone is weak, but req chrome helps.
        if "myworkdayjobs.com" in url:
            return "workday"
        if re.search(r"job\s+requisition\s+id|time\s+type", text, re.I):
            return "workday"

    if (
        "greenhouse.io" in url
        or "gh_jid=" in url
        or re.search(r"powered\s+by\s+greenhouse", text, re.I)
    ):
        return "greenhouse"

    if "icims.com" in url or re.search(r"powered\s+by\s+icims", text, re.I):
        return "icims"

    return "generic"


def _label_value(text, labels, max_chars=120):
    """Return text after a label (same line or next non-empty line)."""
    label_re = "|".join(re.escape(l) for l in labels)
    # Same line: "Label: value" or "Label  value"
    m = re.search(
        rf"(?:^|\n)\s*(?:{label_re})\s*[:\-]?\s*(.+?)(?:\n|$)",
        text,
        re.I,
    )
    if m:
        val = m.group(1).strip()
        if val and not re.match(rf"^(?:{label_re})$", val, re.I):
            return val[:max_chars].strip()
    return None


def _location_type(text):
    """Guess onsite / hybrid / remote from keywords (hybrid before remote)."""
    if re.search(r"\bhybrid\b", text, re.I):
        return "hybrid"
    if re.search(r"\bremote\b", text, re.I):
        return "remote"
    if re.search(r"\b(on-?site|in-?office|in-?person)\b", text, re.I):
        return "onsite"
    return None


def _pay(text):
    """Find a $-denominated pay snippet."""
    m = re.search(
        r"\$\s?\d[\d,]*(?:\.\d+)?\s?[kK]?"
        r"(?:\s?[-\u2013to]+\s?\$?\s?\d[\d,]*(?:\.\d+)?\s?[kK]?)?"
        r"(?:\s?(?:/|per\s+)?(?:hour|hr|year|yr|annually))?",
        text,
        re.I,
    )
    return m.group(0).strip() if m else None


def _city_st(text):
    """Find a City, ST location."""
    m = re.search(r"([A-Z][A-Za-z.\- ]+,\s*[A-Z]{2})\b", text)
    return m.group(1).strip() if m else None


def _parse_date_snippet(raw):
    """Normalize a short date string to YYYY-MM-DD when possible, else raw text."""
    if not raw:
        return None
    raw = raw.strip()
    # Already ISO-ish
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        return m.group(1)
    # MM/DD/YYYY or M/D/YY
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", raw)
    if m:
        mo, day, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if yr < 100:
            yr += 2000
        return f"{yr:04d}-{mo:02d}-{day:02d}"
    # Month DD, YYYY
    m = re.search(
        r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+(\d{1,2}),?\s+(\d{4})\b",
        raw,
        re.I,
    )
    if m:
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        mo = months[m.group(1)[:3].lower()]
        return f"{int(m.group(3)):04d}-{mo:02d}-{int(m.group(2)):02d}"
    return raw[:40]


def _posted_date(text):
    """Extract posted date after common labels."""
    raw = _label_value(
        text,
        ["Posted Date", "Date Posted", "Posted On", "Posted", "Date posted"],
    )
    return _parse_date_snippet(raw) if raw else None


def _application_deadline(text):
    """Extract application deadline after common labels."""
    raw = _label_value(
        text,
        [
            "Application Deadline",
            "Application Close Date",
            "Apply By",
            "Apply by",
            "Closing Date",
            "Close Date",
            "Deadline",
        ],
    )
    return _parse_date_snippet(raw) if raw else None


def _department(text):
    """Extract department / team after common labels."""
    return _label_value(
        text,
        ["Department", "Team", "Organization", "Business Unit", "Job Family"],
        max_chars=80,
    )


def _us_citizen_required(text):
    """True if JD clearly requires US citizenship; False if it says not required; else None."""
    if re.search(
        r"u\.?s\.?\s+citizenship\s+(is\s+)?required|"
        r"must\s+be\s+a?\s*u\.?s\.?\s+citizen|"
        r"only\s+u\.?s\.?\s+citizens|"
        r"u\.?s\.?\s+citizen(?:ship)?\s+required",
        text,
        re.I,
    ):
        return True
    if re.search(
        r"u\.?s\.?\s+citizenship\s+(is\s+)?not\s+required|"
        r"citizenship\s+not\s+required|"
        r"do\s+not\s+require\s+u\.?s\.?\s+citizenship",
        text,
        re.I,
    ):
        return False
    return None


def _shared_from_text(text):
    """Fill fields that are shared across all formats."""
    return {
        "location_type": _location_type(text),
        "pay": _pay(text),
        "location": _city_st(text),
        "posted_date": _posted_date(text),
        "application_deadline": _application_deadline(text),
        "department": _department(text),
        "us_citizen_required": _us_citizen_required(text),
    }


def _extract_workday(text, url=None):
    """Label-anchored Workday extractor; req id also from URL trailing _CODE."""
    fields = dict(EMPTY_FIELDS)
    fields.update(_shared_from_text(text))

    # Title is usually the biggest early heading; Workday page title is often the role.
    first = text.splitlines()[0].strip() if text.splitlines() else ""
    # Strip "Job Details" / site chrome if present.
    if first and not re.search(r"myworkday|job details|careers", first, re.I):
        fields["role"] = first
    else:
        for line in text.splitlines()[1:8]:
            line = line.strip()
            if len(line) > 8 and not re.search(
                r"requisition|time type|posted|locations?|apply", line, re.I
            ):
                fields["role"] = line
                break

    loc = _label_value(text, ["Locations", "Location", "Primary Location"])
    if loc:
        fields["location"] = loc
    fields["job_id"] = _label_value(
        text, ["Job Requisition ID", "Requisition ID", "Job Id", "Job ID"]
    )
    # URL: ..._R000137235 or ..._JR3587
    if url:
        m = re.search(r"_([A-Z]{1,3}\d{3,})\s*(?:/|$|\?)", url, re.I)
        if m and not fields["job_id"]:
            fields["job_id"] = m.group(1)
        # Tenant subdomain often encodes company: axos.wd5.myworkdayjobs.com
        host = urlparse(url).hostname or ""
        m = re.match(r"([a-z0-9-]+)\.wd\d+\.myworkdayjobs\.com", host, re.I)
        if m:
            fields["company"] = m.group(1).replace("-", " ").title()

    dept = _label_value(text, ["Job Family", "Department", "Worker Sub-Type"])
    if dept:
        fields["department"] = dept
    return fields


def _extract_greenhouse(text, url=None):
    """Greenhouse extractor; gh_jid and board slug from URL when present."""
    fields = dict(EMPTY_FIELDS)
    fields.update(_shared_from_text(text))

    first = text.splitlines()[0].strip() if text.splitlines() else ""
    # Titles like "Role at Company" or "Role - Company | Greenhouse"
    clean = re.sub(r"\s*[|\u2013\-]\s*Greenhouse.*$", "", first, flags=re.I).strip()
    split = re.split(r"\s+[-|\u2013\u2014]\s+|\s+at\s+", clean, maxsplit=1)
    if len(split) == 2:
        fields["role"], fields["company"] = split[0].strip(), split[1].strip()
    elif clean:
        fields["role"] = clean

    loc = _label_value(text, ["Location", "Locations"])
    if loc:
        fields["location"] = loc

    if url:
        qs = parse_qs(urlparse(url).query)
        if "gh_jid" in qs:
            fields["job_id"] = qs["gh_jid"][0]
        path = urlparse(url).path or ""
        # boards.greenhouse.io/stripe/jobs/123
        m = re.search(r"greenhouse\.io/([^/]+)", url, re.I)
        if m and not fields["company"]:
            fields["company"] = m.group(1).replace("-", " ").title()
        m = re.search(r"/jobs/(\d+)", path)
        if m and not fields["job_id"]:
            fields["job_id"] = m.group(1)

    if not fields["job_id"]:
        m = re.search(r"(?:job|opening)\s*(?:id|#)?\s*[:#]?\s*(\d{4,})", text, re.I)
        if m:
            fields["job_id"] = m.group(1)
    return fields


def _extract_icims(text, url=None):
    """iCIMS extractor; numeric job id from /jobs/{id}/ path."""
    fields = dict(EMPTY_FIELDS)
    fields.update(_shared_from_text(text))

    first = text.splitlines()[0].strip() if text.splitlines() else ""
    clean = re.sub(r"\s*[|\u2013\-]\s*.*icims.*$", "", first, flags=re.I).strip()
    # "Role in City | Careers at Company"
    m = re.search(r"careers\s+at\s+(.+)$", clean, re.I)
    if m:
        fields["company"] = m.group(1).strip()
        clean = re.sub(r"\s*[|\u2013\-]\s*careers\s+at\s+.+$", "", clean, flags=re.I)
    m = re.search(r"^(.+?)\s+in\s+[A-Z]", clean)
    if m and len(m.group(1)) > 3:
        fields["role"] = m.group(1).strip()
    elif clean:
        fields["role"] = clean

    loc = _label_value(text, ["Job Location", "Location", "Locations"])
    if loc:
        fields["location"] = loc
    fields["job_id"] = _label_value(text, ["Job ID", "Job Id", "ID"])
    if url:
        m = re.search(r"/jobs/(\d+)", url)
        if m:
            fields["job_id"] = fields["job_id"] or m.group(1)
        # careers-appliedsystems.icims.com → Appliedsystems guess
        host = urlparse(url).hostname or ""
        m = re.match(r"careers-([a-z0-9-]+)\.icims\.com", host, re.I)
        if m and not fields["company"]:
            fields["company"] = m.group(1).replace("-", " ").title()
    return fields


def _extract_generic(text):
    """Original regex heuristics for unknown formats."""
    fields = dict(EMPTY_FIELDS)
    fields.update(_shared_from_text(text))
    if not text:
        return fields

    first = text.splitlines()[0].strip() if text.splitlines() else ""
    split = re.split(r"\s+[-|\u2013\u2014]\s+|\s+at\s+", first, maxsplit=1)
    if len(split) == 2:
        fields["role"], fields["company"] = split[0].strip(), split[1].strip()
    elif first:
        fields["role"] = first

    job_id = re.search(
        r"(?:job|req(?:uisition)?)\s*(?:id|number|no\.?|#)?\s*[:#]?\s*([A-Za-z0-9\-]{3,})",
        text,
        re.I,
    )
    if job_id:
        fields["job_id"] = job_id.group(1).strip()
    return fields


def extract_fields(text, url=None):
    """Detect JD format and return inferred application fields.

    `url` improves detection and fills job_id / company from the path.
    Unknown formats fall back to generic regex.
    """
    fmt = detect_format(url=url, text=text)
    if fmt == "workday":
        return _extract_workday(text, url)
    if fmt == "greenhouse":
        return _extract_greenhouse(text, url)
    if fmt == "icims":
        return _extract_icims(text, url)
    return _extract_generic(text)
