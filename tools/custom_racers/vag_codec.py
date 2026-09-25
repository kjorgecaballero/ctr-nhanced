#!/usr/bin/env python3
"""
vag_codec.py — WAV <-> VAG (PSX SPU ADPCM) encoder/decoder.

Part of the VAG project. See docs/VAG_CONTEXT.md for the full plan.

VAG format:
  [48-byte header, little-endian]
   0x00  4  magic       b"VAGp"
   0x04  4  version     0x00000020
   0x08  4  reserved    0
   0x0C  4  dataSize    bytes of ADPCM data (multiple of 16)
   0x10  4  sampleRate  e.g. 44100
   0x14 12  reserved    0
   0x20 16  name        ASCII, NUL-padded
  [N x 16-byte ADPCM blocks]
   byte 0: shift (low nibble) | filter (high nibble)
   byte 1: flags (bit 0 = last block, bit 1 = loop end,
                  bit 2 = loop start, bit 3 = loop repeat)
   bytes 2..15: 28 4-bit signed samples packed low-nibble-first

Each block decodes to 28 16-bit signed PCM samples at sampleRate.

The encoder is a brute-force search over (shift, filter) per block,
minimizing L2 error vs the input PCM. Same approach as xa_codec.py.
"""

from __future__ import annotations

import argparse
import struct
import sys
import wave
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# Format constants
# ---------------------------------------------------------------------------

VAG_MAGIC = b"VAGp"
VAG_VERSION = 0x00000020
VAG_HEADER_SIZE = 48
VAG_BLOCK_SIZE = 16
VAG_SAMPLES_PER_BLOCK = 28

# Filter coefficients in Q6 from psx-spx:
#   https://psx-spx.consoledev.net/soundprocessingunitspu/#spu-adpcm-samples
VAG_FILTERS = (
    (0,   0),    # 0
    (60,  0),    # 1
    (115, -52),  # 2
    (98,  -55),  # 3
    (122, -60),  # 4
)

SHIFT_MIN = 0
SHIFT_MAX = 12


# ---------------------------------------------------------------------------
# Encoder
# ---------------------------------------------------------------------------

def _encode_block(target, old, older, shift, filt):
    """
    Encode 28 target samples with a fixed (shift, filter).

    target: sequence of 28 ints (16-bit signed range)
    old, older: previous two decoded samples (history)
    Returns (nibbles, decoded) — both length 28.
    """
    f0, f1 = VAG_FILTERS[filt]
    nibbles = []
    decoded = []
    for i in range(VAG_SAMPLES_PER_BLOCK):
        pred = (old * f0 + older * f1 + 32) >> 6
        desired = target[i] - pred
        if shift <= 12:
            divisor = 1 << (12 - shift)
            half = divisor >> 1
            if desired >= 0:
                nibble = (desired + half) // divisor
            else:
                nibble = -((-desired + half) // divisor)
        else:
            nibble = desired << (shift - 12)
        if nibble > 7:
            nibble = 7
        elif nibble < -8:
            nibble = -8
        nibbles.append(nibble)
        contribution = (nibble << 12) >> shift
        s = pred + contribution
        if s > 32767:
            s = 32767
        elif s < -32768:
            s = -32768
        decoded.append(s)
        older = old
        old = s
    return nibbles, decoded


def _block_error(target, decoded):
    err = 0
    for i in range(VAG_SAMPLES_PER_BLOCK):
        d = target[i] - decoded[i]
        err += d * d
    return err


def _encode_block_best(target, old, older):
    """Brute-force search for the best (shift, filter).
    Returns (nibbles, decoded, shift, filter)."""
    best = None
    best_err = None
    for shift in range(SHIFT_MIN, SHIFT_MAX + 1):
        for filt in range(len(VAG_FILTERS)):
            nibbles, decoded = _encode_block(target, old, older, shift, filt)
            err = _block_error(target, decoded)
            if best_err is None or err < best_err:
                best_err = err
                best = (nibbles, decoded, shift, filt)
    return best


def encode_vag(pcm, sample_rate=44100, name="vag_sample", loop=False):
    """
    Encode mono int16 PCM to VAG bytes.

    pcm: numpy int16 1D array (mono)
    sample_rate: header field only (no resampling)
    name: 16-char ASCII name for the header
    loop: if True, mark the first block as loop-start and the last
          block as loop-end + loop-repeat, so the SPU emulator
          loops the sample indefinitely when loop_addr is set.
    Returns: bytes (the full VAG file)
    """
    pcm = np.asarray(pcm, dtype=np.int16)
    if pcm.ndim != 1:
        raise ValueError(f"expected 1D PCM, got shape {pcm.shape}")

    pad = (-len(pcm)) % VAG_SAMPLES_PER_BLOCK
    if pad:
        pcm = np.concatenate([pcm, np.zeros(pad, dtype=np.int16)])

    n_blocks = len(pcm) // VAG_SAMPLES_PER_BLOCK
    data_size = n_blocks * VAG_BLOCK_SIZE

    name_bytes = name.encode("ascii", errors="replace")[:16]
    name_bytes = name_bytes + b"\x00" * (16 - len(name_bytes))
    header = struct.pack(
        "<4sIIII12s16s",
        VAG_MAGIC,
        VAG_VERSION,
        0,              # reserved
        data_size,
        sample_rate,
        b"\x00" * 12,   # reserved
        name_bytes,
    )
    if len(header) != VAG_HEADER_SIZE:
        raise AssertionError(f"header size mismatch: {len(header)}")

    body = bytearray()
    old = 0
    older = 0
    for bi in range(n_blocks):
        start = bi * VAG_SAMPLES_PER_BLOCK
        end = start + VAG_SAMPLES_PER_BLOCK
        target = [int(x) for x in pcm[start:end]]
        nibbles, decoded, shift, filt = _encode_block_best(target, old, older)
        older = decoded[-2]
        old = decoded[-1]

        is_first = bi == 0
        is_last = bi == n_blocks - 1
        if loop:
            # Bit 0 = last block (stop), bit 1 = loop end,
            # bit 2 = loop start, bit 3 = loop repeat.
            flags = 0x00
            if is_first: flags |= 0x04
            if is_last:  flags |= 0x03   # loop end + last block
        else:
            flags = 0x01 if is_last else 0x00
        body.append(((filt & 0x0F) << 4) | (shift & 0x0F))
        body.append(flags)
        for i in range(0, VAG_SAMPLES_PER_BLOCK, 2):
            n0 = nibbles[i] & 0x0F
            n1 = nibbles[i + 1] & 0x0F
            body.append((n1 << 4) | n0)

    if len(body) != data_size:
        raise AssertionError(f"body size mismatch: {len(body)} != {data_size}")

    return bytes(header) + bytes(body)


# ---------------------------------------------------------------------------
# Decoder
# ---------------------------------------------------------------------------

def decode_vag(vag_data):
    """
    Decode VAG bytes to mono int16 PCM.
    Returns (pcm numpy int16 1D, sample_rate int).
    """
    if len(vag_data) < VAG_HEADER_SIZE:
        raise ValueError(f"VAG data too short: {len(vag_data)} < {VAG_HEADER_SIZE}")

    magic, version, reserved, data_size, sample_rate, reserved12, name = \
        struct.unpack_from("<4sIIII12s16s", vag_data, 0)

    if magic != VAG_MAGIC:
        raise ValueError(f"bad VAG magic: {magic!r}")
    if data_size % VAG_BLOCK_SIZE != 0:
        raise ValueError(f"data_size {data_size} not a multiple of {VAG_BLOCK_SIZE}")
    if len(vag_data) < VAG_HEADER_SIZE + data_size:
        raise ValueError(
            f"truncated VAG: need {VAG_HEADER_SIZE + data_size}, "
            f"file is {len(vag_data)}"
        )

    body = vag_data[VAG_HEADER_SIZE:VAG_HEADER_SIZE + data_size]
    n_blocks = data_size // VAG_BLOCK_SIZE

    pcm = np.empty(n_blocks * VAG_SAMPLES_PER_BLOCK, dtype=np.int16)
    old = 0
    older = 0
    out_idx = 0
    for bi in range(n_blocks):
        base = bi * VAG_BLOCK_SIZE
        shift = body[base] & 0x0F
        filt = (body[base] >> 4) & 0x0F
        if filt >= len(VAG_FILTERS):
            filt = 0
        f0, f1 = VAG_FILTERS[filt]
        for i in range(VAG_SAMPLES_PER_BLOCK):
            byte_idx = base + 2 + (i >> 1)
            if (i & 1) == 0:
                nibble = body[byte_idx] & 0x0F
            else:
                nibble = (body[byte_idx] >> 4) & 0x0F
            nibble_signed = nibble - 16 if (nibble & 0x08) else nibble
            pred = (old * f0 + older * f1 + 32) >> 6
            contribution = (nibble_signed << 12) >> shift
            s = pred + contribution
            if s > 32767:
                s = 32767
            elif s < -32768:
                s = -32768
            pcm[out_idx] = s
            out_idx += 1
            older = old
            old = s

    return pcm, sample_rate


# ---------------------------------------------------------------------------
# WAV helpers
# ---------------------------------------------------------------------------

def _read_wav_mono16(path):
    with wave.open(str(path), "rb") as w:
        n_channels = w.getnchannels()
        sample_width = w.getsampwidth()
        sample_rate = w.getframerate()
        n_frames = w.getnframes()
        data = w.readframes(n_frames)

    if sample_width != 2:
        raise ValueError(f"expected 16-bit WAV, got {sample_width * 8}-bit")

    pcm = np.frombuffer(data, dtype=np.int16)
    if n_channels == 2:
        pcm = pcm.reshape(-1, 2).mean(axis=1).astype(np.int16)
    elif n_channels != 1:
        raise ValueError(f"unsupported channel count: {n_channels}")

    return pcm, sample_rate


def _write_wav_mono16(path, pcm, sample_rate):
    pcm = np.asarray(pcm, dtype=np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------------------
# SNR
# ---------------------------------------------------------------------------

def _snr_db(reference, test):
    n = min(len(reference), len(test))
    a = np.asarray(reference[:n], dtype=np.float64)
    b = np.asarray(test[:n], dtype=np.float64)
    err = a - b
    energy = float(np.sum(a * a))
    err_energy = float(np.sum(err * err))
    if err_energy <= 0:
        return float("inf")
    if energy <= 0:
        return float("-inf")
    return 10.0 * np.log10(energy / err_energy)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resample_linear(pcm, src_rate, dst_rate):
    """Linear-interpolation resample. pcm is int16 mono. Cheap, and
    22050 vs 44100 halves the VAG size with acceptable quality for
    short SFX. For music we would want a proper resampler, but this
    is only used for dance SFX that need to fit in 24 KB of SPU RAM."""
    if src_rate == dst_rate or len(pcm) == 0:
        return pcm
    ratio = float(dst_rate) / float(src_rate)
    n_out = int(round(len(pcm) * ratio))
    if n_out <= 0:
        return pcm[:0]
    x_src = np.arange(len(pcm), dtype=np.float64)
    x_dst = np.arange(n_out, dtype=np.float64) / ratio
    out = np.interp(x_dst, x_src, pcm.astype(np.float64))
    return np.clip(np.round(out), -32768, 32767).astype(np.int16)


def cmd_encode(args):
    pcm, sr = _read_wav_mono16(args.input)
    src_sr = sr
    target = getattr(args, "rate", 0) or 0
    if target > 0 and target != sr:
        pcm = _resample_linear(pcm, sr, target)
        sr = target
    name = Path(args.output).stem[:16]
    vag = encode_vag(pcm, sample_rate=sr, name=name, loop=getattr(args, "loop", False))
    Path(args.output).write_bytes(vag)
    print(f"encode: {args.input} -> {args.output}")
    if src_sr != sr:
        print(f"  resample: {src_sr} Hz -> {sr} Hz")
    print(f"  input:  {len(pcm)} samples, {sr} Hz, {pcm.nbytes} bytes")
    print(f"  output: {len(vag)} bytes "
          f"({VAG_HEADER_SIZE} header + {len(vag) - VAG_HEADER_SIZE} data)")
    return 0


def cmd_decode(args):
    vag = Path(args.input).read_bytes()
    pcm, sr = decode_vag(vag)
    _write_wav_mono16(args.output, pcm, sr)
    print(f"decode: {args.input} -> {args.output}")
    print(f"  output: {len(pcm)} samples, {sr} Hz")
    return 0


def cmd_roundtrip(args):
    pcm_orig, sr = _read_wav_mono16(args.input)
    n_orig = len(pcm_orig)
    name = Path(args.input).stem[:16]
    vag = encode_vag(pcm_orig, sample_rate=sr, name=name)
    pcm_dec, sr_dec = decode_vag(vag)
    _write_wav_mono16(args.output, pcm_dec, sr_dec)

    snr = _snr_db(pcm_orig.astype(np.float64), pcm_dec[:n_orig].astype(np.float64))

    print(f"roundtrip: {args.input} -> {args.output}")
    print(f"  input:     {n_orig} samples, {sr} Hz")
    print(f"  decoded:   {len(pcm_dec)} samples (incl. padding), {sr_dec} Hz")
    print(f"  VAG size:  {len(vag)} bytes")
    print(f"  SNR:       {snr:.2f} dB")

    pcm_bytes = n_orig * 2
    ratio = len(vag) / pcm_bytes if pcm_bytes else 0.0
    print(f"  compression: {pcm_bytes} -> {len(vag)} bytes ({ratio:.3f}x)")

    return 0 if snr >= 15.0 else 1


def cmd_test(args):
    vag = Path(args.input).read_bytes()
    pcm, sr = decode_vag(vag)
    peak = int(np.max(np.abs(pcm.astype(np.int32)))) if len(pcm) else 0
    rms = float(np.sqrt(np.mean(pcm.astype(np.float64) ** 2))) if len(pcm) else 0.0
    print(f"test: {args.input}")
    print(f"  size:     {len(vag)} bytes")
    print(f"  samples:  {len(pcm)} ({len(pcm) / sr:.3f} s at {sr} Hz)")
    print(f"  peak:     {peak} / 32767")
    print(f"  rms:      {rms:.1f}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="WAV <-> VAG (PSX SPU ADPCM) codec")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_enc = sub.add_parser("encode", help="encode WAV -> VAG")
    p_enc.add_argument("input")
    p_enc.add_argument("output")
    p_enc.add_argument("--loop", action="store_true",    
                       help="mark the sample for infinite looping")
    p_enc.add_argument("--rate", type=int, default=0,
                       help="resample to this rate before encoding "
                            "(0 = keep the input rate)")
    p_enc.set_defaults(func=cmd_encode)

    p_dec = sub.add_parser("decode", help="decode VAG -> WAV")
    p_dec.add_argument("input")
    p_dec.add_argument("output")
    p_dec.set_defaults(func=cmd_decode)

    p_rt = sub.add_parser("roundtrip", help="encode + decode + SNR check")
    p_rt.add_argument("input")
    p_rt.add_argument("output")
    p_rt.set_defaults(func=cmd_roundtrip)

    p_test = sub.add_parser("test", help="print stats about a VAG file")
    p_test.add_argument("input")
    p_test.set_defaults(func=cmd_test)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())