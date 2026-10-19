"""Exact integer model and full-size synthetic fixtures, not pretrained data."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np

ROWS, INNER, COLS, FRAC = 99, 64, 256, 8


def encode_q8_8(values: np.ndarray) -> np.ndarray:
    """Encode finite real values: nearest, ties away from zero, saturating."""
    a = np.asarray(values, dtype=np.float64)
    if not np.isfinite(a).all():
        raise ValueError("Inputs must be finite")
    # Clip before conversion, so arbitrarily large finite inputs cannot wrap int64.
    scaled = np.clip(a * 256.0, -32768.0, 32767.0)
    rounded = np.copysign(np.floor(np.abs(scaled) + 0.5), scaled)
    return rounded.astype(np.int16)


def requantize(acc: np.ndarray) -> tuple[np.ndarray, int]:
    acc = np.asarray(acc, dtype=np.int64)
    magnitude = (np.abs(acc) + 128) // 256
    rounded = np.where(acc < 0, -magnitude, magnitude)
    saturated = int(np.count_nonzero((rounded < -32768) | (rounded > 32767)))
    return np.clip(rounded, -32768, 32767).astype(np.int16), saturated


def linear_q8_8(x: np.ndarray, w: np.ndarray, bias: np.ndarray) -> tuple[np.ndarray, int]:
    if x.shape != (ROWS, INNER) or w.shape != (INNER, COLS) or bias.shape != (COLS,):
        raise ValueError("Expected X=(99,64), W=(64,256), bias=(256,)")
    for a in (x, w, bias):
        if not np.issubdtype(a.dtype, np.integer):
            raise ValueError("linear_q8_8 requires already encoded integer inputs")
        if (a < -32768).any() or (a > 32767).any():
            raise ValueError("Encoded values must fit signed 16 bits")
    # Independent of RTL scheduling: compute the entire integer matrix in int64.
    acc = x.astype(np.int64) @ w.astype(np.int64) + bias.astype(np.int64) * 256
    if np.abs(acc).max() >= 2**39:
        raise AssertionError("Accumulator exceeds the RTL 40-bit contract")
    return requantize(acc)


def write_hex(path: Path, values: np.ndarray) -> None:
    path.write_text("".join(f"{int(v) & 0xffff:04x}\n" for v in values.flat), encoding="ascii")


def save_case(directory: Path, layer: int, x: np.ndarray, w: np.ndarray,
              bias: np.ndarray, name: str) -> dict:
    y, saturations = linear_q8_8(x, w, bias)
    for kind, values in (("x", x), ("w", w), ("b", bias), ("y", y)):
        write_hex(directory / f"layer_{layer:02d}_{kind}.hex", values)
    (directory / f"layer_{layer:02d}_sat.hex").write_text(f"{saturations:08x}\n", encoding="ascii")
    return {"layer": layer, "case": name, "saturations": saturations,
            "outputs": int(y.size), "output_min": int(y.min()), "output_max": int(y.max())}


def generate_vectors(directory: Path, layers: int = 12, seed: int = 20261018) -> list[dict]:
    if not 1 <= layers <= 12:
        raise ValueError("layers must be between 1 and 12")
    directory.mkdir(parents=True, exist_ok=True)
    manifests = []
    for layer in range(layers):
        rng = np.random.default_rng(seed + 7919 * layer)
        x = rng.integers(-768, 769, size=(ROWS, INNER), dtype=np.int16)
        w = rng.integers(-32, 33, size=(INNER, COLS), dtype=np.int16)
        bias = rng.integers(-128, 129, size=COLS, dtype=np.int16)
        name = "dense_signed_random"
        if layer == 0:
            # Products vanish; every output must equal its column's signed bias.
            x.fill(0)
            bias = np.resize(np.array([-32768, 32767, -1, 0, 1, 256, -256], dtype=np.int16), COLS)
            name = "zero_input_and_bias_broadcast"
        elif layer == 1:
            # Force a 64*(-32768)*(-32768)=2**36 positive dot and its negative
            # counterpart, as well as cancellation and mixed-lane saturation.
            x.fill(-32768)
            w[:, 0::4] = -32768
            w[:, 1::4] = 32767
            w[:, 2::4] = 0
            w[:, 3::4] = np.resize(np.array([-32768, 32767], dtype=np.int16), INNER)[:, None]
            bias = np.resize(np.array([32767, -32768, 123, -123], dtype=np.int16), COLS)
            name = "full_width_accumulation_and_saturation"
        elif layer == 2:
            x.fill(0)
            x[:, 0] = 1
            w[0] = np.resize(np.array([127, 128, 129, -127, -128, -129, 384, -384], dtype=np.int16), COLS)
            bias.fill(0)
            name = "positive_and_negative_half_lsb_ties"
        manifests.append(save_case(directory, layer, x, w, bias, name))
    (directory / "manifest.json").write_text(json.dumps({
        "source": "synthetic_full_size_not_pretrained", "seed": seed,
        "format": "signed16_fractional8_nearest_ties_away_saturate",
        "X": [ROWS, INNER], "W": [INNER, COLS], "Y": [ROWS, COLS], "cases": manifests,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifests


def check_numeric_contract() -> None:
    # Explicit expected values, independent of the RTL implementation.
    inputs = np.array([0, 127, 128, 129, -127, -128, -129, 384, -384,
                       32767*256+127, 32767*256+128,
                       -32768*256-127, -32768*256-128,
                       2**36, -(2**36)], dtype=np.int64)
    expected = [0, 0, 1, 1, 0, -1, -1, 2, -2, 32767, 32767, -32768, -32768, 32767, -32768]
    result, saturated = requantize(inputs)
    if result.tolist() != expected or saturated != 4:
        raise AssertionError((result.tolist(), saturated))
    values = encode_q8_8(np.array([0.5/256, -0.5/256, 1e30, -1e30]))
    if values.tolist() != [1, -1, 32767, -32768]:
        raise AssertionError(values)
