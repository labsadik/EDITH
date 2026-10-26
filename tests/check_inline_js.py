from html.parser import HTMLParser
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


class InlineScriptParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.scripts = []
        self._current = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script":
            attributes = dict(attrs)
            self._current = [] if "src" not in attributes else None

    def handle_data(self, data):
        if self._current is not None:
            self._current.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script":
            if self._current is not None:
                script = "".join(self._current).strip()
                if script:
                    self.scripts.append(script)
            self._current = None


def main():
    checked = 0
    with tempfile.TemporaryDirectory() as tmp:
        for relative in ("dashboard/static/app.html", "dashboard/static/login.html"):
            parser = InlineScriptParser()
            parser.feed((ROOT / relative).read_text(encoding="utf-8"))
            for idx, script in enumerate(parser.scripts, start=1):
                script_path = Path(tmp) / f"{Path(relative).stem}-{idx}.js"
                script_path.write_text(script, encoding="utf-8")
                subprocess.run(["node", "--check", str(script_path)], check=True)
                checked += 1
    print(f"Checked JavaScript syntax in {checked} inline script(s).")


if __name__ == "__main__":
    main()
