"""Bit-accurate contract for signed16 x signed16 dot64 and bias/requant.

No zero point. Real = code * 2**(-fraction_bits). Dense kernel is [K,N].
MAC wraps in signed40 after each accepted product; bias addition uses signed41.
Requant is round-to-nearest, ties away from zero, followed by signed16 saturation.
"""
import numpy as np

def wrap(value, bits):
    return (int(value) + (1 << (bits-1))) % (1 << bits) - (1 << (bits-1))

def round_away(x):
    x = np.asarray(x, dtype=np.float64)
    if not np.all(np.isfinite(x)):
        raise ValueError('Non-finite input')
    return np.copysign(np.floor(np.abs(x) + .5), x)

def encode(x, frac, bits=16):
    scaled = round_away(np.asarray(x, dtype=np.float64) * (2.0 ** frac))
    return np.clip(scaled, -(1 << (bits-1)), (1 << (bits-1))-1).astype(np.int64)

def choose_frac(max_abs, headroom=1.25):
    if not np.isfinite(max_abs) or max_abs < 0:
        raise ValueError('Invalid calibration range')
    return int(np.clip(np.floor(np.log2(32767.0 / max(max_abs*headroom, 1e-12))), 0, 24))

def requant(acc, bias, shift):
    if not 0 <= shift <= 63:
        raise ValueError('shift must be 0..63')
    acc = np.asarray(acc, dtype=np.int64)
    bias = np.asarray(bias, dtype=np.int64)
    if np.any(acc < -(1<<39)) or np.any(acc >= (1<<39)):
        raise ValueError('acc out of signed40')
    if np.any(bias < -(1<<39)) or np.any(bias >= (1<<39)):
        raise ValueError('bias out of signed40')
    total = acc + bias  # signed41, always exact in int64
    mag = np.abs(total)
    if shift:
        mag = (mag + (1 << (shift-1))) >> shift
    rounded = np.where(total < 0, -mag, mag)
    return np.clip(rounded, -32768, 32767).astype(np.int64)

def dot64_scalar(x, w):
    if len(x) != 64 or len(w) != 64:
        raise ValueError('Exactly 64 operands required')
    acc = 0
    for a, b in zip(x, w):
        if not -32768 <= int(a) <= 32767 or not -32768 <= int(b) <= 32767:
            raise ValueError('Operand out of signed16')
        acc = wrap(acc + int(a)*int(b), 40)
    return acc

def linear(xq, wq, bq, shift):
    xq, wq = np.asarray(xq, dtype=np.int64), np.asarray(wq, dtype=np.int64)
    if xq.shape[-1] != 64 or wq.shape != (64,256):
        raise ValueError('Expected [...,64] @ [64,256]')
    if np.any(xq < -32768) or np.any(wq < -32768) or np.any(xq > 32767) or np.any(wq > 32767):
        raise ValueError('Operand out of signed16')
    # 64 signed16 products fit signed38, so no signed40 MAC step can overflow.
    # This vectorization is exactly equivalent to the sequential scalar MAC.
    return requant(xq @ wq, bq, shift)

def nrmse(y, reference):
    a, b = np.asarray(y, dtype=np.float64), np.asarray(reference, dtype=np.float64)
    return float(np.sqrt(np.mean((a-b)**2))/max(float(np.sqrt(np.mean(b*b))),1e-8))

def write_hex(path, values, bits):
    mask = (1 << bits)-1
    path.write_text(''.join(('%0*x\n' % ((bits+3)//4, int(v)&mask)) for v in np.asarray(values).reshape(-1)), encoding='ascii')
