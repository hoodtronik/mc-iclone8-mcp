r"""Bundle the scraped docs (docs/hoodtronik/manual/{wiki,ic8}/*.md) into one markdown file per manual section, sized for
NotebookLM sources (a notebook holds ~50 sources; a section bundle is one source). Output: docs/hoodtronik/manual/bundles/.
  python scripts/bundle_docs.py
# CLAUDE-NOTE (2026-10-07): the bundles are gitignored with the rest of docs/hoodtronik/manual (Reallusion's copyright).
"""
import os, re
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "hoodtronik", "manual")
OUT = os.path.join(ROOT, "bundles")
MAX_CHARS = 1_500_000   # NotebookLM text/markdown sources accept ~500k words; stay well under


def main():
    os.makedirs(OUT, exist_ok=True)
    groups = defaultdict(list)
    for sub, prefix in (("wiki", "RLPy-wiki"), ("ic8", None)):
        d = os.path.join(ROOT, sub)
        for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if not f.endswith(".md"):
                continue
            key = prefix or re.sub(r"__.*$", "", f)          # ic8 files are named <section>__<topic>.md
            groups[key].append(os.path.join(d, f))
    written = []
    for key, files in sorted(groups.items()):
        text, part = "", 1
        for path in files:
            body = open(path, encoding="utf-8").read()
            if len(text) + len(body) > MAX_CHARS and text:
                written.append(_write(key, part, text)); text, part = "", part + 1
            text += body + "\n\n---\n\n"
        if text:
            written.append(_write(key, part, text))
    print(f"{len(written)} bundles from {sum(len(v) for v in groups.values())} pages")
    for w in written:
        print(" ", os.path.basename(w), f"{os.path.getsize(w) // 1024} KB")


def _write(key, part, text):
    name = f"iClone8_{key}" + (f"_part{part}" if part > 1 else "") + ".md"
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# iClone 8 documentation bundle: {key}\n\n{text}")
    return path


if __name__ == "__main__":
    main()
