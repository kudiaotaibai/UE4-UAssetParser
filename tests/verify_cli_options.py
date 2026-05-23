import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from properties import PropertyParseOptions, read_raw_blob


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = Path(
    os.environ.get(
        "UASSET_SAMPLE",
        r"D:\vr\ZMKJBS\Content\Blueprints\Global\Module\Character\BP_Character.uasset",
    )
)
SAMPLE_DIR = SAMPLE.parent
OUTPUT = ROOT / "output" / "cli-tests"


def run_cmd(args):
    return subprocess.run(
        [sys.executable, "-m", "src.main", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class FakeReader:
    def __init__(self, payload):
        self.payload = payload
        self.pos = 0

    def tell(self):
        return self.pos

    def readBytes(self, count):
        chunk = self.payload[self.pos:self.pos + count]
        self.pos += len(chunk)
        return chunk


def main():
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)

    summary_json = OUTPUT / "summary.json"
    result = run_cmd([
        str(SAMPLE),
        "-o",
        str(summary_json),
        "--summary-only",
        "--compact",
    ])
    assert result.returncode == 0, result.stderr
    summary = load_json(summary_json)
    assert summary["packageName"].endswith("/BP_Character")
    assert summary["exportCount"] == 499
    assert "objectTree" not in summary
    assert "exportTable" in summary

    blueprint_json = OUTPUT / "blueprint_only.json"
    result = run_cmd([
        str(SAMPLE),
        "-o",
        str(blueprint_json),
        "--blueprint-only",
        "--no-raw",
        "--compact",
    ])
    assert result.returncode == 0, result.stderr
    blueprint = load_json(blueprint_json)
    assert "summary" not in blueprint
    assert "objectTree" not in blueprint
    assert "CollisionCylinder" in blueprint
    assert blueprint["CollisionCylinder"]["Class"] == "CapsuleComponent"

    no_raw_json = OUTPUT / "no_raw.json"
    result = run_cmd([
        str(SAMPLE),
        "-o",
        str(no_raw_json),
        "--no-raw",
        "--compact",
    ])
    assert result.returncode == 0, result.stderr
    no_raw_text = no_raw_json.read_text(encoding="utf-8")
    assert '"rawData"' not in no_raw_text

    limited_json = OUTPUT / "limited_raw.json"
    result = run_cmd([
        str(SAMPLE),
        "-o",
        str(limited_json),
        "--raw-limit",
        "8",
        "--compact",
    ])
    assert result.returncode == 0, result.stderr
    load_json(limited_json)

    fake = FakeReader(b"0123456789abcdef")
    raw = read_raw_blob(
        fake,
        16,
        16,
        PropertyParseOptions(include_raw=True, raw_limit=8),
    )
    assert raw["rawSize"] == 16
    assert raw["rawData"] == b"01234567".hex()
    assert raw["rawDataTruncated"] is True

    batch_dir = OUTPUT / "batch"
    result = run_cmd([
        str(SAMPLE_DIR),
        "--batch",
        "-o",
        str(batch_dir),
        "--summary-only",
        "--compact",
    ])
    assert result.returncode == 0, result.stderr
    assert (batch_dir / "BP_Character.json").exists()

    bad_file = OUTPUT / "bad.uasset"
    bad_file.write_text("hello", encoding="ascii")
    result = run_cmd([str(bad_file)])
    assert result.returncode == 3
    assert "magic tag mismatch" in result.stderr

    print("=== CLI options verified OK ===")


if __name__ == "__main__":
    main()
