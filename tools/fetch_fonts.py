"""Download the bundled Thai UI font (IBM Plex Sans Thai, SIL Open Font License 1.1).

Fonts are redistributable under the OFL; OFL.txt is stored next to them and
copied into the installer.
"""
from __future__ import annotations

import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "src", "vmi", "resources", "fonts")
BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexsansthai/"
FILES = ["IBMPlexSansThai-Regular.ttf", "IBMPlexSansThai-Medium.ttf",
         "IBMPlexSansThai-SemiBold.ttf", "IBMPlexSansThai-Bold.ttf", "OFL.txt"]


def main():
    os.makedirs(DEST, exist_ok=True)
    for f in FILES:
        out = os.path.join(DEST, f)
        if os.path.exists(out) and os.path.getsize(out) > 0:
            continue
        print("download", f)
        with urllib.request.urlopen(BASE + f, timeout=60) as r:
            data = r.read()
        if f.endswith(".ttf") and data[:4] not in (b"\x00\x01\x00\x00", b"true", b"OTTO"):
            sys.exit(f"unexpected content for {f}")
        with open(out, "wb") as fh:
            fh.write(data)
    print("fonts in", DEST)


if __name__ == "__main__":
    main()
