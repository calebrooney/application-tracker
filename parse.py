"""Local, no-API-key job description capture + field inference.

Grab JD text two ways:
- parse_link: fetch a URL and extract visible page text (title first).
- ocr_image: run Tesseract OCR on a screenshot.

Then extract_fields runs simple regex heuristics over that text to
prefill the application form. It is best-effort: unknown fields are None
and the user validates/edits everything before saving.
"""

import re

import requests
from bs4 import BeautifulSoup

# Pretend to be a normal browser so more sites return real HTML.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def parse_link(url):
    """Fetch a URL and return its visible text, page title prepended.

    Strips scripts/styles and collapses whitespace. The <title> is put on
    the first line because it often reads "Role - Company" and helps the
    field extractor. JS-heavy boards may return little text; the screenshot
    path is the reliable fallback.
    """
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Grab the title before stripping tags.
    title = soup.title.get_text(strip=True) if soup.title else ""

    # Drop non-content tags before pulling text.
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # Collapse blank lines so the stored text stays readable.
    lines = [line.strip() for line in soup.get_text("\n").splitlines()]
    body = "\n".join(line for line in lines if line)
    return f"{title}\n{body}" if title else body


def ocr_image(path):
    """Run Tesseract OCR on an image file and return the detected text.

    Imports are local so the web app still starts if Tesseract/Pillow
    are not installed until the OCR feature is actually used.
    """
    import pytesseract
    from PIL import Image

    return pytesseract.image_to_string(Image.open(path)).strip()


def extract_fields(text):
    """Guess application fields from raw JD text using regex heuristics.

    Returns a dict with keys role, company, location, location_type, pay,
    and job_id. Any field we can't confidently find is None so the form
    just shows a blank for the user to fill in.
    """
    fields = {
        "role": None,
        "company": None,
        "location": None,
        "location_type": None,
        "pay": None,
        "job_id": None,
    }
    if not text:
        return fields

    # First line is usually the page title: "Role - Company" / "Role at Company".
    first = text.splitlines()[0].strip() if text.splitlines() else ""
    split = re.split(r"\s+[-|\u2013\u2014]\s+|\s+at\s+", first, maxsplit=1)
    if len(split) == 2:
        fields["role"], fields["company"] = split[0].strip(), split[1].strip()
    elif first:
        fields["role"] = first

    # Work/location arrangement keyword anywhere in the text.
    if re.search(r"\bremote\b", text, re.I):
        fields["location_type"] = "remote"
    elif re.search(r"\bhybrid\b", text, re.I):
        fields["location_type"] = "hybrid"
    elif re.search(r"\b(on-?site|in-?office|in-?person)\b", text, re.I):
        fields["location_type"] = "onsite"

    # "City, ST" pattern (two-letter state) is a decent location guess.
    city = re.search(r"([A-Z][A-Za-z.\- ]+,\s*[A-Z]{2})\b", text)
    if city:
        fields["location"] = city.group(1).strip()

    # Pay: salary range or hourly rate with a leading $.
    pay = re.search(
        r"\$\s?\d[\d,]*(?:\.\d+)?\s?[kK]?"
        r"(?:\s?[-\u2013to]+\s?\$?\s?\d[\d,]*(?:\.\d+)?\s?[kK]?)?"
        r"(?:\s?(?:/|per\s+)?(?:hour|hr|year|yr|annually))?",
        text,
        re.I,
    )
    if pay:
        fields["pay"] = pay.group(0).strip()

    # Job / requisition id near a label, or a bare "R123456"-style code.
    job_id = re.search(
        r"(?:job|req(?:uisition)?)\s*(?:id|number|no\.?|#)?\s*[:#]?\s*([A-Za-z0-9\-]{3,})",
        text,
        re.I,
    )
    if job_id:
        fields["job_id"] = job_id.group(1).strip()

    return fields
