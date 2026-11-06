"""Check repository-local Markdown links without making network requests."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    errors = []
    files = [ROOT / "README.md", ROOT / "AGENTS.md", *sorted((ROOT / "docs").rglob("*.md"))]
    files += [ROOT / "evaluation/PROTOCOL.md"]
    count = 0
    for file in files:
        if not file.exists():
            errors.append(f"Missing {file.relative_to(ROOT)}")
            continue
        text = file.read_text()
        if text.count("```") % 2:
            errors.append(f"Unbalanced code fence: {file.relative_to(ROOT)}")
        for destination in re.findall(r"\]\(([^)]+)\)", text):
            if destination.startswith(("https://", "http://", "#", "mailto:")):
                continue
            target = file.parent / destination.split("#")[0]
            if not target.exists():
                errors.append(f"Broken link in {file.relative_to(ROOT)}: {destination}")
            count += 1
    for error in errors:
        print(error, file=sys.stderr)
    print(f"Checked {len(files)} Markdown files and {count} local links.")
    sys.exit(bool(errors))


if __name__ == "__main__":
    main()
