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
    """Prompt for text; Enter keeps default (or None if blank with no default)."""
    hint = f" [{default}]" if default else ""
    value = input(f"{label}{hint}: ").strip()
    if value:
        return value
    return default


def ask_choice(label, options, default=None):
    """Prompt with a numbered menu; Enter keeps default."""
    print(f"\n{label}:")
    for i, opt in enumerate(options, start=1):
        mark = " *" if opt == default else ""
        print(f"  {i}) {opt}{mark}")
    while True:
        raw = input("Choose a number (Enter to keep): ").strip()
        if not raw:
            return default
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
        raise RuntimeError(
            "No image on the clipboard. Copy a screenshot (Cmd+Ctrl+Shift+4, "
            "or Copy in Preview), then press Enter at the screenshot prompt."
        )
    return dest


def resolve_screenshot(raw):
    """Turn a path or empty Enter (clipboard) into a local image path for OCR."""
    if raw:
        path = normalize_path(raw)
        if not path or not os.path.isfile(path):
            raise FileNotFoundError(f"File not found: {path or raw}")
        dest = os.path.join(UPLOAD_DIR, os.path.basename(path))
        # Skip copy when the file is already under uploads/.
        if os.path.abspath(path) != os.path.abspath(dest):
            shutil.copy2(path, dest)
        return dest, os.path.basename(path)
    print("Reading image from clipboard...")
    dest = save_clipboard_image()
    return dest, os.path.basename(dest)


def capture():
    """Read a link and/or screenshot, infer fields, confirm, and insert."""
    db.init_db()
    print("New application — paste a link and/or screenshot\n")
    print(
        "Tip: Cmd+V cannot paste a photo into the terminal. "
        "Copy the image, then press Enter at the screenshot prompt "
        "(or paste a file path instead).\n"
    )

    link = ask_text("Job posting link")
    # Empty Enter with no link → read PNG from macOS clipboard.
    screenshot = ask_text("Screenshot path (or Enter to use clipboard image)")

    # Path pasted into the link field (common) → treat as screenshot.
    if link:
        link_as_file = normalize_path(link)
        if link_as_file and os.path.isfile(link_as_file):
            if not screenshot:
                screenshot = link
            link = None

    parts = []
    sources = []
    try:
        if link:
            print("Reading link...")
            parts.append(parse.parse_link(link))
            sources.append(link)

        # Path given → OCR it. No path and no link → clipboard image.
        if screenshot or not link:
            path, name = resolve_screenshot(screenshot)
            print("Running OCR...")
            parts.append(parse.ocr_image(path))
            sources.append(name)

        if not parts:
            print("Need a link or a screenshot.")
            return
    except Exception as err:
        print(f"Could not read the posting: {err}")
        return

    text = "\n\n".join(parts)
    source = " + ".join(sources)

    data = parse.extract_fields(text)
    data["link"] = link
    data["job_description"] = text
    data["jd_source"] = source
    data["app_date"] = date.today().isoformat()
    data["status"] = "applied"
    data["energy_related"] = False
    data["due_date"] = None

    print("\nInferred fields — press Enter to keep, or type a new value.\n")
    data["role"] = ask_text("Role", data.get("role"))
    data["company"] = ask_text("Company", data.get("company"))
    data["location"] = ask_text("Location", data.get("location"))
    data["location_type"] = ask_choice(
        "Location type", db.LOCATION_TYPES, data.get("location_type")
    )
    data["pay"] = ask_text("Pay", data.get("pay"))
    data["app_date"] = ask_text("Application date (YYYY-MM-DD)", data["app_date"])
    data["due_date"] = ask_text("Due date (YYYY-MM-DD)", data.get("due_date"))
    data["job_id"] = ask_text("Job / req id", data.get("job_id"))
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
