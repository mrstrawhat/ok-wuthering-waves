"""Command-line regression checks. Never launch, capture or send input to a game."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=Path(__file__).resolve().parents[1] / ".build-native/debug/okww-mac-probe")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    results = []

    def check(name, command, expected_code, verify):
        result = subprocess.run([str(binary), *command], capture_output=True, text=True, timeout=10)
        passed = result.returncode == expected_code and verify(result)
        results.append({"name": name, "passed": passed, "exit_code": result.returncode,
                        "stdout": result.stdout, "stderr": result.stderr})

    def failed_with(message):
        def verify(result):
            data = json.loads(result.stderr)
            return data.get("ok") is False and message in data.get("error", "")
        return verify

    with tempfile.TemporaryDirectory(prefix="okww-probe-cli-") as temp:
        root = Path(temp)
        valid = root / "valid.json"
        valid.write_text(json.dumps({"schemaVersion": 1, "actions": [
            {"kind": "key", "keys": ["escape"], "durationMs": 100},
            {"kind": "wait", "durationMs": 300},
        ]}))
        common = ["--image-width", "1920", "--image-height", "1080"]
        check("help_does_not_require_game", ["help"], 0, lambda r: "NEVER launches" in r.stdout)
        check("offline_script_validation", ["validate", "--script", str(valid), *common], 0,
              lambda r: json.loads(r.stdout)["durationMs"] == 400
              and len(json.loads(r.stdout)["events"]) == 2)
        check("unknown_command", ["unknown-command"], 2, failed_with("Unknown command"))
        check("duplicate_options", ["validate", "--script", str(valid), "--script", str(valid), *common],
              2, failed_with("Duplicate option"))
        check("nonfinite_image_size", ["validate", "--script", str(valid), "--image-width", "nan",
                                       "--image-height", "1080"], 2, failed_with("finite number"))
        unknown = root / "unknown.json"
        unknown.write_text('{"schemaVersion":1,"actions":[{"kind":"key","keys":["w"],"durationMS":100}]}')
        check("unknown_script_field", ["validate", "--script", str(unknown), *common],
              2, failed_with("Unknown action field"))
        invalid = root / "invalid.json"
        invalid.write_text(json.dumps({"schemaVersion": 1, "actions": [
            {"kind": "key", "keys": ["w"]}, {"kind": "click", "x": 9, "y": 0.5},
        ]}))
        # Even the execute flag must not bypass whole-script validation.
        check("invalid_execute_rejected_before_target_lookup",
              ["input", "--script", str(invalid), *common, "--execute"],
              2, failed_with("Normalized coordinates"))
        oversized = root / "oversized.json"
        oversized.write_bytes(b" " * 65537)
        check("oversized_script", ["validate", "--script", str(oversized), *common],
              2, failed_with("64KiB"))
        # This deliberately nonexistent ID cannot bind to or launch the actual game.
        check("missing_app_is_not_launched", ["windows", "--bundle", "org.okww.offline-test.nonexistent-7ce1948f"],
              2, failed_with("No app was launched"))

    report = {"binary": str(binary), "checks": len(results),
              "passed": sum(r["passed"] for r in results), "results": results,
              "game_launched": False, "screen_capture_requested": False, "native_input_requested": False}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(text + "\n")
    print(text)
    return 0 if report["passed"] == report["checks"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
