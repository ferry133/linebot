"""Smoke test: verify bot can load the knowledge base via the symlink.

Run: python3 tests/smoke_knowledge.py
Exits non-zero on failure so it can be used in CI/pre-commit.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KDIR = os.path.join(ROOT, "knowledge")
FM = re.compile(r"^---\n.*?\n---\n", re.DOTALL)

EXPECTED_FILES = {
    "01_service_process.md",
    "02_construction_steps.md",
    "03_pricing.md",
    "04_design_vs_turnkey.md",
    "05_contract_guide.md",
    "06_inspection_guide.md",
}

EXPECTED_KEYWORDS = ["服務流程", "工序", "報價", "設計", "合約", "驗收"]

failures = []


def check(cond, msg):
    print(("PASS" if cond else "FAIL") + f": {msg}")
    if not cond:
        failures.append(msg)


def main():
    check(os.path.islink(KDIR) or os.path.isdir(KDIR), f"knowledge dir exists: {KDIR}")
    real = os.path.realpath(KDIR)
    check("wiki/public" in real, f"symlink resolves into vault: {real}")

    found = {f for f in os.listdir(KDIR) if f.endswith(".md")}
    missing = EXPECTED_FILES - found
    check(not missing, f"all expected .md present (missing: {missing or 'none'})")

    parts = []
    for fname in sorted(found):
        with open(os.path.join(KDIR, fname), encoding="utf-8") as fh:
            body = FM.sub("", fh.read(), count=1)
            parts.append(body)
            check("---" not in body[:10], f"{fname}: frontmatter stripped")

    combined = "\n\n---\n\n".join(parts)
    check(len(combined) > 5000, f"combined knowledge > 5000 chars (got {len(combined)})")

    for kw in EXPECTED_KEYWORDS:
        check(kw in combined, f"keyword '{kw}' present in knowledge")

    photos = os.path.join(KDIR, "project_photos.yaml")
    check(os.path.isfile(photos), "project_photos.yaml present")

    print()
    if failures:
        print(f"{len(failures)} failure(s):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All smoke checks passed.")


if __name__ == "__main__":
    main()
