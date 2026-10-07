# iClone 8 documentation corpus (for agents)

Before probing RLPy for a creator-visible feature, read how iClone itself does it. Lesson of 2026-10-07: the RLPy FBX
conversion call failed on Mixamo files while the manual's *Convert External Motion* feature (with a Mixamo preset) was the
working route the whole time.

## Sources

| Source | URL | Notes |
| --- | --- | --- |
| iClone 8 manual (English) | https://manual.reallusion.com/iClone-8/Content/ENU/8.0/ | MadCap site; `https://manual.reallusion.com/iClone-8/sitemap.xml` lists every topic (838 ENU 8.0 topics) |
| RLPy API wiki (generic) | https://wiki.reallusion.com/IC_Python_API | class pages `IC_Python_API:RLPy_<Class>` |
| RLPy API wiki (iClone 8 specific) | https://wiki.reallusion.com/IC_8_Python_API | `IC8_Python_API:RLPy_<Class>` pages override the generic ones; tutorials: Custom FPS, End Effector Animation, Facial Animation, Smart Content Manager |
| Installed stub | `C:\Program Files\Reallusion\iClone 8\Bin64\RLPy.py` | the only complete signature list; empty-docstring `*args` overloads need the TypeError trick |

## Local scrape (gitignored)

```text
python scripts/scrape_docs.py wiki                                   # -> docs/hoodtronik/manual/wiki/*.md
python scripts/scrape_docs.py manual docs/hoodtronik/manual/manual_urls.txt   # -> docs/hoodtronik/manual/ic8/*.md
python scripts/bundle_docs.py                                        # -> docs/hoodtronik/manual/bundles/*.md (one per section)
```

`docs/hoodtronik/manual/` is in `.gitignore`: it is Reallusion's copyrighted text and this repository is public. Re-run the
three commands on a fresh clone. Grep the folder (`rg -i "convert external motion" docs/hoodtronik/manual`) before
declaring anything missing.

## NotebookLM

Notebook **iClone 8 docs - manual + RLPy API**, id `3c5ecc64-67b0-4e69-ba37-8df578de9e70`
(https://notebook.google.com/notebook/3c5ecc64-67b0-4e69-ba37-8df578de9e70), fed with the section bundles. Ask it
workflow questions ("how do I attach an object to a path and animate it?") through the notebooklm MCP `notebook_query`
or `uvx --from notebooklm-mcp-cli nlm notebook query <id> "<question>"`.

## Workflow for a new capability

1. Query the notebook / grep the bundles: what is the UI feature called, which panel, which dialog, which options?
2. Grep `RLPy.py` for the owning class; read the wiki page; recover hidden overloads with a deliberate mis-call.
3. If RLPy has no setter, find the Qt widget (dock/dialog objectNames) — see the agent reference §8 for the probing recipes.
4. Prove at runtime (read-back or render), then write the tool, its test, and the matrix row.
