"""Convert one extracted real-model layer to the exact RTL format and reference.

Input NPZ arrays: X[99,64], W[64,256], b[256], finite floating-point values.
No preprocessing or neural-network arithmetic is moved into the RTL adapter.
"""
from pathlib import Path
import argparse
import json
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from reference import encode_q8_8, save_case  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--layer", type=int, default=0, choices=range(12))
    args = parser.parse_args()
    with np.load(args.input, allow_pickle=False) as data:
        x, w, bias = (np.asarray(data[key], dtype=np.float64) for key in ("X", "W", "b"))
    encoded = tuple(encode_q8_8(a) for a in (x, w, bias))
    args.output.mkdir(parents=True, exist_ok=True)
    result = save_case(args.output, args.layer, *encoded, "extracted_model_layer")
    # A single-layer diagnostic, not the contest's aggregate 12-layer/600-sample score.
    from reference import linear_q8_8
    output, _ = linear_q8_8(*encoded)
    reference = x @ w + bias
    nrmse = float(np.sqrt(np.mean((output.astype(float)/256-reference)**2)) /
                  max(1e-8, float(np.sqrt(np.mean(reference**2)))))
    result["single_input_float_reference_nrmse"] = nrmse
    result["input_file"] = str(args.input.resolve())
    (args.output / f"layer_{args.layer:02d}_conversion.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
