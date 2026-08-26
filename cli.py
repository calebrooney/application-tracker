"""CLI capture flow: paste a link and/or screenshot, confirm fields, save.

Run via `applied` (or `python cli.py`). No browser.
"""

import os
import shutil
import subprocess
from datetime import date, datetime
from urllib.parse import unquote, urlparse

import db
import parse

# Screenshots copied here so paths stay project-local (same as the web app).
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def ask_text(label, default=None):
    """Prompt for text: Enter keeps default, `-` clears, anything else replaces."""
    hint = f" [{default}]" if default else ""
    value = input(f"{label}{hint}: ").strip()
    if value == "-":
        return None
    if value:
        return value
    return default


def ask_choice(label, options, default=None):
    """Numbered menu: Enter keeps default, `-` clears, number picks."""
    print(f"\n{label}:")
    for i, opt in enumerate(options, start=1):
        mark = " *" if opt == default else ""
        print(f"  {i}) {opt}{mark}")
    while True:
        raw = input("Choose a number (Enter keep, - clear): ").strip()
        if not raw:
            return default
        if raw == "-":
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("Invalid choice, try again.")


def ask_yes_no(label, default=False):
    """Prompt y/n; Enter keeps default."""
    suffix = "Y/n" if default else "y/N"
    raw = input(f"{label} ({suffix}): ").strip().lower()
    if not raw:
        return default
    return raw.startswith("y")


def normalize_path(raw):
    """Clean a pasted/drag-dropped path (quotes, ~, file://, escaped spaces)."""
    if not raw:
        return None
    path = raw.strip()
    # Finder/Terminal often wraps the path in matching quotes.
    if len(path) >= 2 and path[0] == path[-1] and path[0] in "\"'":
        path = path[1:-1]
    if path.lower().startswith("file:"):
        path = unquote(urlparse(path).path)
    path = os.path.expanduser(path)
    # Terminal drag-drop escapes spaces as "\ ".
    path = path.replace("\\ ", " ")
    return path


def save_clipboard_image():
    """Save a PNG from the macOS clipboard into uploads/. Return the path.

    Uses AppleScript («class PNGf»). Raises RuntimeError if the clipboard
    has no image (Cmd+V of a photo into the terminal never works as text).
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(UPLOAD_DIR, f"clipboard_{stamp}.png")
    # POSIX path escaped for AppleScript string literal
    posix = dest.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
    try
        set pngData to the clipboard as «class PNGf»
    on error
        error "no image"
    end try
    set outFile to POSIX file "{posix}"
    set fileRef to open for access outFile with write permission
    try
        set eof of fileRef to 0
        write pngData to fileRef
    end try
    close access fileRef
    '''
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not os.path.isfile(dest) or os.path.getsize(dest) == 0:
        raise RuntimeError("no image")
    return dest


def save_clipboard_pdf():
    """Save a PDF from the macOS clipboard into uploads/. Return the path.

    Expects pasteboard type com.adobe.pdf (from Print → Copy PDF to Clipboard).
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(UPLOAD_DIR, f"clipboard_{stamp}.pdf")
    dest_esc = __import__("json").dumps(dest)
    result = subprocess.run(
        [
            "osascript",
            "-l",
            "JavaScript",
            "-e",
            f"""
ObjC.import('AppKit');
ObjC.import('Foundation');
var pb = $.NSPasteboard.generalPasteboard;
var data = pb.dataForType($('com.adobe.pdf'));
if (!data || data.length === 0) {{ throw new Error('no pdf'); }}
var ok = data.writeToFileAtomically({dest_esc}, true);
if (!ok) {{ throw new Error('write failed'); }}
""",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not os.path.isfile(dest) or os.path.getsize(dest) == 0:
        raise RuntimeError("no pdf")
    return dest


def read_clipboard_capture():
    """Pull PDF or PNG from the clipboard into uploads/. Prefer PDF."""
    try:
        print("Reading PDF from clipboard...")
        return save_clipboard_pdf(), "pdf"
    except RuntimeError:
        pass
    try:
        print("Reading image from clipboard...")
        return save_clipboard_image(), "image"
    except RuntimeError:
        pass
    raise RuntimeError(
        "Clipboard has no PDF or image.\n"
        "  • PDF: Cmd+P → PDF → Copy PDF to Clipboard, then Enter here.\n"
        "  • Image: copy a screenshot, then Enter here."
    )


def text_from_file(path):
    """OCR an image or extract text from a PDF at path."""
    lower = path.lower()
    if lower.endswith(".pdf"):
        print("Extracting text from PDF...")
        text = parse.pdf_text(path)
        # Clipboard PDFs are ephemeral — drop the temp copy after extract.
        if os.path.basename(path).startswith("clipboard_"):
            try:
                os.remove(path)
            except OSError:
                pass
        if not text:
            raise RuntimeError(
                "PDF had no extractable text (likely a scan). "
                "Use a screenshot + OCR instead."
            )
        return text
    print("Running OCR...")
    return parse.ocr_image(path)


def resolve_capture(raw):
    """Path or empty Enter (clipboard PDF/image) → local file for parsing."""
    if raw:
        path = normalize_path(raw)
        if not path or not os.path.isfile(path):
            raise FileNotFoundError(f"File not found: {path or raw}")
        dest = os.path.join(UPLOAD_DIR, os.path.basename(path))
        if os.path.abspath(path) != os.path.abspath(dest):
            shutil.copy2(path, dest)
        return dest, os.path.basename(path)
    dest, _kind = read_clipboard_capture()
    return dest, os.path.basename(dest)


def capture():
    """Read a link and/or screenshot/PDF, infer fields, confirm, and insert."""
    db.init_db()
    print("New application — paste a link and/or screenshot/PDF\n")
    print(
        "Tips:\n"
        "  • Cmd+V cannot paste a photo/PDF into the terminal.\n"
        "  • PDF: Cmd+P → PDF → Copy PDF to Clipboard, then Enter below.\n"
        "  • Image: copy a screenshot, then Enter (or paste a file path).\n"
    )

    link = ask_text("Job posting link")
    # Empty Enter with no link → read PDF/PNG from macOS clipboard.
    media = ask_text("Screenshot/PDF path (or Enter to use clipboard)")

    # Path pasted into the link field (common) → treat as media.
    if link:
        link_as_file = normalize_path(link)
        if link_as_file and os.path.isfile(link_as_file):
            if not media:
                media = link
            link = None

    parts = []
    sources = []
    try:
        if link:
            print("Reading link...")
            parts.append(parse.parse_link(link))
            sources.append(link)

        # Path given → parse it. No path and no link → clipboard PDF/image.
        if media or not link:
            path, name = resolve_capture(media)
            parts.append(text_from_file(path))
            sources.append(name)

        if not parts:
            print("Need a link, screenshot, or PDF.")
            return
    except Exception as err:
        print(f"Could not read the posting: {err}")
        return

    text = "\n\n".join(parts)
    source = " + ".join(sources)

    data = parse.extract_fields(text, url=link)
    data["link"] = link
    data["job_description"] = text
    data["jd_source"] = source
    data["app_date"] = date.today().isoformat()
    data["status"] = "applied"
    data["energy_related"] = False
    data["due_date"] = None

    print(
        "\nInferred fields — Enter keep, - reject/clear, or type a new value.\n"
    )
    # Drop every inferred guess; keep JD text/source and today's app date.
    if ask_yes_no("Reject all inferred fields and enter manually?", False):
        keep_jd = data.get("job_description")
        keep_src = data.get("jd_source")
        keep_link = data.get("link")
        data = {
            "role": None,
            "company": None,
            "location": None,
            "location_type": None,
            "pay": None,
            "department": None,
            "posted_date": None,
            "application_deadline": None,
            "app_date": date.today().isoformat(),
            "due_date": None,
            "job_id": None,
            "us_citizen_required": None,
            "link": keep_link,
            "energy_related": False,
            "status": "applied",
            "job_description": keep_jd,
            "jd_source": keep_src,
        }

    data["role"] = ask_text("Role", data.get("role"))
    data["company"] = ask_text("Company", data.get("company"))
    data["location"] = ask_text("Location", data.get("location"))
    data["location_type"] = ask_choice(
        "Location type", db.LOCATION_TYPES, data.get("location_type")
    )
    data["pay"] = ask_text("Pay", data.get("pay"))
    data["department"] = ask_text("Department / team", data.get("department"))
    data["posted_date"] = ask_text(
        "Posted date (YYYY-MM-DD)", data.get("posted_date")
    )
    data["application_deadline"] = ask_text(
        "Application deadline (YYYY-MM-DD)", data.get("application_deadline")
    )
    data["app_date"] = ask_text("Application date (YYYY-MM-DD)", data["app_date"])
    data["due_date"] = ask_text("Due date (YYYY-MM-DD)", data.get("due_date"))
    data["job_id"] = ask_text("Job / req id", data.get("job_id"))
    # Tri-state: Enter keeps; - clears; y/n overrides.
    us_default = data.get("us_citizen_required")
    us_hint = (
        "yes" if us_default is True else "no" if us_default is False else None
    )
    us_raw = ask_text("US citizen required (yes/no)", us_hint)
    if us_raw is None:
        # `-` clears when a hint was shown; bare Enter with no hint keeps None.
        data["us_citizen_required"] = None if us_hint is not None else us_default
    elif us_raw.lower().startswith("y"):
        data["us_citizen_required"] = True
    elif us_raw.lower().startswith("n"):
        data["us_citizen_required"] = False
    else:
        data["us_citizen_required"] = us_default
    data["link"] = ask_text("Link", data.get("link"))
    data["energy_related"] = ask_yes_no("Energy related?", data["energy_related"])
    data["status"] = (
        ask_choice("Status", db.STATUSES, data["status"]) or "applied"
    )

    if not ask_yes_no("Save this application?", True):
        print("Cancelled.")
        return

    app_id = db.add_application(data)
    role = data.get("role") or "(no role)"
    company = data.get("company") or "(no company)"
    print(f"\nLogged #{app_id}: {role} @ {company}")


def main():
    """Entry point for `applied` / `python cli.py`."""
    capture()


if __name__ == "__main__":
    main()
