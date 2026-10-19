"""Generate vectors, compile, run Icarus, and independently compare all outputs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from reference import generate_vectors, check_numeric_contract  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layers", type=int, default=12, choices=range(1, 13))
    parser.add_argument("--waves", action="store_true", help="Write compact control VCD")
    parser.add_argument("--vectors", type=Path, help="Use existing layer_XX_[x,w,b,y,sat].hex fixtures")
    args = parser.parse_args()
    iverilog, vvp = shutil.which("iverilog"), shutil.which("vvp")
    if not iverilog or not vvp:
        parser.error("Install Icarus Verilog and put iverilog/vvp on PATH")
    check_numeric_contract()
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    vectors = args.vectors.resolve() if args.vectors else build / "vectors"
    if not args.vectors:
        generate_vectors(vectors, args.layers)
    for layer in range(args.layers):
        for name, count in (("x", 6336), ("w", 16384), ("b", 256), ("y", 25344), ("sat", 1)):
            file = vectors / f"layer_{layer:02d}_{name}.hex"
            if not file.is_file() or len(file.read_text().split()) != count:
                parser.error(f"Missing or wrong-size fixture: {file}")
    executable = build / "ffn.vvp"
    sources = [ROOT / "rtl/ffn_numeric_pkg.sv", ROOT / "rtl/ffn_sram_1rw.sv",
               ROOT / "rtl/ffn_accel.sv", ROOT / "tb/tb_ffn_accel.sv"]
    command = [iverilog, "-g2012", "-s", "tb_ffn_accel", "-o", str(executable), *map(str, sources)]
    compilation = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
    (build / "compile.log").write_text(compilation.stdout + compilation.stderr, encoding="utf-8")
    if compilation.returncode:
        print(compilation.stdout + compilation.stderr)
        return compilation.returncode
    command = [vvp, str(executable), f"+VECTORS={vectors.as_posix()}",
               f"+RESULTS={build.as_posix()}", f"+LAYERS={args.layers}"]
    if args.waves:
        command.append("+WAVES")
    print(f"Running {args.layers} full-size layers, 25,344 outputs per layer", flush=True)
    start = time.perf_counter()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, cwd=ROOT)
    lines = []
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
        lines.append(line)
    return_code = process.wait()
    elapsed = time.perf_counter() - start
    (build / "simulation.log").write_text("".join(lines), encoding="utf-8")
    if return_code or "ALL TESTS PASSED" not in "".join(lines):
        return return_code or 1
    checks = []
    for layer in range(args.layers):
        expected = (vectors / f"layer_{layer:02d}_y.hex").read_text().split()
        actual = (build / f"rtl_layer_{layer:02d}.hex").read_text().split()
        if len(actual) != 25344 or actual != expected:
            raise AssertionError(f"Independent file comparison failed: layer {layer}")
        checks.append({"layer": layer, "outputs_compared": len(actual), "mismatches": 0})
    with (build / "performance.csv").open(newline="") as f:
        performance = list(csv.DictReader(f))
    version_result = subprocess.run([iverilog, "-V"], capture_output=True, text=True)
    report = {"status": "PASS", "simulator": version_result.stdout.splitlines()[0],
              "numpy_version": np.__version__,
              "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sources},
              "host": platform.platform(), "wall_seconds": round(elapsed, 3),
              "data_source": "provided_vectors" if args.vectors else "synthetic_full_size",
              "shapes": {"X": [99, 64], "W": [64, 256], "Y": [99, 256]},
              "layers": args.layers, "total_outputs_compared": args.layers * 25344,
              "bit_mismatches": 0, "checks": checks, "performance": performance,
              "nominal_clock_hz": 150_000_000,
              "timing_closure_verified": False, "real_pretrained_accuracy_verified": False}
    (build / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"PASS: {args.layers*25344:,} bit-exact outputs; report: {build/'summary.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
