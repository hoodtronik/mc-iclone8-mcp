r"""Scrape the Reallusion RLPy wiki (and, given a URL list, the iClone 8 manual) into plain-text markdown for grep and for
NotebookLM sources. Output: docs/hoodtronik/manual/{wiki,ic8}/*.md (GITIGNORED - Reallusion's copyright).
  python scripts/scrape_docs.py wiki                 # all IC_Python_API / IC8_Python_API class + tutorial pages
  python scripts/scrape_docs.py manual urls.txt      # one manual topic URL per line
# CLAUDE-NOTE (2026-10-07): stdlib only (urllib + html.parser) so it runs anywhere; polite 0.4 s delay between requests.
"""
import html, os, re, sys, time, urllib.parse, urllib.request
from html.parser import HTMLParser

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "hoodtronik", "manual")
UA = {"User-Agent": "Mozilla/5.0 (mc-iclone8-mcp docs scrape; personal reference)"}


class _Text(HTMLParser):
    SKIP = {"script", "style", "nav", "header", "footer", "noscript"}
    BLOCK = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "pre", "br", "table", "ul", "ol", "dd", "dt"}

    def __init__(self):
        super().__init__(); self.out, self.skip, self.pre = [], 0, 0
    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP: self.skip += 1
        if tag == "pre": self.pre += 1
        if tag in ("h1", "h2", "h3", "h4"): self.out.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag in ("li",): self.out.append("\n- ")
        elif tag in ("td", "th"): self.out.append(" | ")
        elif tag in self.BLOCK: self.out.append("\n")
    def handle_endtag(self, tag):
        if tag in self.SKIP: self.skip -= 1
        if tag == "pre": self.pre -= 1; self.out.append("\n")
        if tag in self.BLOCK: self.out.append("\n")
    def handle_data(self, data):
        if self.skip: return
        self.out.append(data if self.pre else re.sub(r"\s+", " ", data))


def fetch(url):
    url = urllib.parse.quote(url, safe=":/%?=&")   # topic names with spaces (e.g. "...Speed Variation on Path.htm")
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")


def to_md(url, raw, title=None):
    body = raw
    m = re.search(r'<div[^>]+id="mw-content-text".*', raw, re.S) or re.search(r'<div[^>]+class="[^"]*body-container[^"]*".*', raw, re.S) or re.search(r"<body.*", raw, re.S)
    if m: body = m.group(0)
    p = _Text(); p.feed(body)
    text = html.unescape("".join(p.out))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    t = title or (re.search(r"<title>(.*?)</title>", raw, re.S) or [None, url])[1]
    return f"# {html.unescape(t).strip()}\n\nSource: {url}\n\n{text}\n"


def save(folder, name, md):
    os.makedirs(os.path.join(OUT, folder), exist_ok=True)
    path = os.path.join(OUT, folder, re.sub(r"[^A-Za-z0-9_.-]+", "_", name) + ".md")
    with open(path, "w", encoding="utf-8") as f: f.write(md)
    return path


WIKI_CLASSES = """RMath RVector2 RVector3 RVector4 RMatrix3 RQuaternion RTransform RRgb RColor RStatus RTime RVariant RFileIO RGlobal
RPyTimer RApplication RIBase RIObject RINode RIMaterialComponent RIProp RIAvatar RICamera RIParticle RILight RISpotLight RIPointLight
RIDirectionalLight RScene RDataBlock RKey RControl RFloatControl RTransformControl RlClip RIClip RISkeletonComponent RVisemeSmoothOption
RIVisemeComponent RIMorphComponent RIHikEffectorComponent RIFaceComponent RPositionSetting RRotationSetting RDeviceSetting RIDeviceBase
RBodySetting RIBodyDevice RHandSetting RIHandDevice RFacialSetting RIFacialDevice RIMocapManager RCallback RWinMessageCallback
RDialogCallback REventCallback REventHandler RPyTimerCallback RIEventListener RIDialog RIDockWidget RUi RIAudioObject RAudioRecorder
RAudio RAudioRecorderCallback RTcpCallback RTcpClient RUdpCallback RUdpClient RLookAtComponent RILookAtComponent RIPath RReachKey
RTick RFps RIVisualSettingComponent RIMotionDirectorManager""".split()
WIKI_TUTORIALS = ["IC_8_Python_API", "IC_8_Python_API:Enforcing_Plugin_Compatibility", "IC_8_Python_API:Dealing_With_Custom_FPS",
                  "IC_8_Python_API:End_Effector_Animation", "IC_8_Python_API:Facial_Animation", "IC_8_Python_API:Smart_Content_Manager",
                  "IC_Python_API:Your_First_iClone_Python_Plugin", "IC_Python_API", "IC_Python_API:RL_Python_Samples"]


def scrape_wiki():
    got, missing = 0, []
    pages = WIKI_TUTORIALS + [f"{ns}:RLPy_{c}" for c in WIKI_CLASSES for ns in ("IC8_Python_API", "IC_Python_API")]
    for page in pages:
        url = "https://wiki.reallusion.com/" + page
        try:
            raw = fetch(url)
            if "There is currently no text in this page" in raw or "noarticletext" in raw:
                missing.append(page); continue
            save("wiki", page.replace(":", "__"), to_md(url, raw)); got += 1
        except Exception as e:
            missing.append(f"{page} ({e})")
        time.sleep(0.4)
    print(f"wiki: saved {got}, missing {len(missing)}"); [print("  -", m) for m in missing]


def scrape_manual(list_file):
    got = 0
    for url in [l.strip() for l in open(list_file, encoding="utf-8") if l.strip() and not l.startswith("#")]:
        try:
            raw = fetch(url)
            if "Page Not Found" in raw[:2000]: print("  404", url); continue
            name = re.sub(r"^.*?/Content/ENU/8\.0/", "", url).rsplit(".", 1)[0].replace("/", "__")
            save("ic8", name, to_md(url, raw)); got += 1
        except Exception as e:
            print("  ERR", url, e)
        time.sleep(0.4)
    print(f"manual: saved {got}")


if __name__ == "__main__":
    {"wiki": lambda: scrape_wiki(), "manual": lambda: scrape_manual(sys.argv[2])}[sys.argv[1]]()
