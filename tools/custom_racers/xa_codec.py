#!/usr/bin/env python3
"""xa_codec.py - Decode/encode PSX XA audio (FORM2 sectors, 4-bit ADPCM, mono 37800 Hz).

Used by the CTR custom racer addon to convert WAV voicelines to XA.

Format recap:
  Sector (2336 bytes):
    - 8 bytes: subheader = file,channel,submode,coding x2
    - 18 frames x 128 bytes
    - 24 bytes: padding (ignored)
  Frame (128 bytes):
    - 4 bytes: header (unused by decoder)
    - 12 bytes: params (8 used at 0,1,2,3,8,9,10,11; 4 ignored)
    - 112 bytes: 28 sample bytes x4 (interleaved per sound-unit pair)
  Sound unit: 28 samples with one (shift, weight) pair.
"""

import argparse
import math
import struct
import wave
from pathlib import Path

XA_FORM2_SECTOR        = 2336
XA_SUBHEADER           = 8
XA_FRAMES_PER_SECTOR   = 18
XA_FRAME_SIZE          = 128
XA_SUBFRAMES_PER_FRAME = 8
XA_SAMPLES_PER_SU      = 28
XA_SAMPLES_PER_FRAME   = XA_SUBFRAMES_PER_FRAME * XA_SAMPLES_PER_SU    # 224
XA_SAMPLES_PER_SECTOR  = XA_FRAMES_PER_SECTOR * XA_SAMPLES_PER_FRAME   # 4032

SAMPLE_RATE = 37800

# 5 predictor weights (from PSX-SPX / vag2wav.c). Coefficients /64.
WEIGHTS = [
    (0,   0),
    (60,  0),
    (115, -52),
    (98,  -55),
    (122, -60),
]


# --- Decoder ------------------------------------------------------------------

def _decode_sector(sector, channel, state):
    """Decode one FORM2 sector. state = [old, older] (mutated)."""
    file_num, ch, submode, coding = sector[0], sector[1], sector[2], sector[3]
    if not (submode & 0x04) or file_num != 1 or ch != channel or ((coding >> 4) & 3) != 0:
        return []

    out = []
    for frame in range(XA_FRAMES_PER_SECTOR):
        fo = XA_SUBHEADER + frame * XA_FRAME_SIZE
        params = sector[fo + 4 : fo + 16]
        for su in range(XA_SUBFRAMES_PER_FRAME):
            pi = (su & 3) | ((su & 4) << 1)
            param = params[pi]
            shift = param & 0xF
            weight = (param >> 4) & 0xF
            if weight > 4:
                weight = 4
            w0, w1 = WEIGHTS[weight]
            for i in range(XA_SAMPLES_PER_SU):
                byte = sector[fo + 16 + i * 4 + (su >> 1)]
                nib = ((byte & 0xF) << 4) if (su & 1) == 0 else (byte & 0xF0)
                nib_s = nib - 0x100 if nib >= 0x80 else nib
                sample = (nib_s * 0x100) >> shift
                sample += (state[0] * w0) >> 6
                sample += (state[1] * w1) >> 6
                if sample > 32767:  sample = 32767
                if sample < -32768: sample = -32768
                out.append(sample)
                state[1] = state[0]
                state[0] = sample
    return out


def decode_xa(data, channel=0):
    """Decode an XA file. Returns list of int16 samples."""
    if len(data) % XA_FORM2_SECTOR != 0:
        raise ValueError(f"XA size {len(data)} not a multiple of {XA_FORM2_SECTOR}")
    state = [0, 0]
    out = []
    for s in range(len(data) // XA_FORM2_SECTOR):
        off = s * XA_FORM2_SECTOR
        out.extend(_decode_sector(data[off:off + XA_FORM2_SECTOR], channel, state))
    return out


# --- Encoder ------------------------------------------------------------------

def _encode_sound_unit(samples, state):
    """Encode 28 samples as one sound unit.

    Brute-force over (weight, shift, 16 nibbles) and pick minimum SSE.
    Returns (param_byte, nibbles[28], new_old, new_older).
    """
    best = None  # (err, param_byte, nibbles, new_old, new_older)
    for weight in range(5):
        w0, w1 = WEIGHTS[weight]
        for shift in range(13):
            o, oo = state[0], state[1]
            err = 0
            nibbles = []
            for s in samples:
                pred = ((o * w0) >> 6) + ((oo * w1) >> 6)
                best_err = None
                best_recon = pred
                best_ns = 0
                for ns in range(-8, 8):
                    delta = (ns * 0x1000) >> shift
                    recon = pred + delta
                    if recon > 32767:  recon = 32767
                    if recon < -32768: recon = -32768
                    e = (recon - s) * (recon - s)
                    if best_err is None or e < best_err:
                        best_err = e
                        best_recon = recon
                        best_ns = ns
                err += best_err
                nibbles.append(best_ns & 0xF)
                oo = o
                o = best_recon
            if best is None or err < best[0]:
                best = (err, ((weight & 0xF) << 4) | (shift & 0xF),
                        nibbles, o, oo)
    return best[1], best[2], best[3], best[4]


def encode_xa(pcm_samples, channel=0):
    """Encode int16 PCM samples to XA FORM2 bytes."""
    n_sectors = max(1, (len(pcm_samples) + XA_SAMPLES_PER_SECTOR - 1) // XA_SAMPLES_PER_SECTOR)
    target = n_sectors * XA_SAMPLES_PER_SECTOR
    pcm = list(pcm_samples) + [0] * (target - len(pcm_samples))

    out = bytearray()
    state = [0, 0]
    idx = 0
    for _ in range(n_sectors):
        sec = bytearray(XA_FORM2_SECTOR)
        for off in (0, 4):  # duplicated subheader
            sec[off + 0] = 1        # file
            sec[off + 1] = channel
            sec[off + 2] = 0x64     # audio + form2 + realtime
            sec[off + 3] = 0x00     # 37800 Hz, 4-bit, mono
        for frame in range(XA_FRAMES_PER_SECTOR):
            fo = XA_SUBHEADER + frame * XA_FRAME_SIZE
            sec[fo + 0] = 0x0C      # frame header, ignored by decoder
            sec[fo + 1] = 0x0C
            sec[fo + 2] = 0x0C
            sec[fo + 3] = 0x0C
            params = bytearray(12)
            data = bytearray(112)
            su_nibbles = []
            for su in range(XA_SUBFRAMES_PER_FRAME):
                chunk = pcm[idx:idx + XA_SAMPLES_PER_SU]
                idx += XA_SAMPLES_PER_SU
                param_byte, nibs, state[0], state[1] = _encode_sound_unit(chunk, state)
                pi = (su & 3) | ((su & 4) << 1)
                params[pi] = param_byte
                su_nibbles.append(nibs)
            for i in range(XA_SAMPLES_PER_SU):
                for p in range(4):
                    lo = su_nibbles[p * 2][i] & 0xF
                    hi = su_nibbles[p * 2 + 1][i] & 0xF
                    data[i * 4 + p] = (hi << 4) | lo
            sec[fo + 4 : fo + 16] = params
            sec[fo + 16 : fo + 128] = data
        out.extend(sec)
    return bytes(out)


# --- WAV I/O ------------------------------------------------------------------

def read_wav(path):
    with wave.open(str(path), "rb") as w:
        n_ch = w.getnchannels()
        sw = w.getsampwidth()
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
    if sw != 2:
        raise ValueError(f"Only 16-bit WAV supported, got {sw*8}-bit")
    n = len(raw) // 2
    samples = list(struct.unpack(f"<{n}h", raw))
    if n_ch == 2:
        samples = [(samples[i*2] + samples[i*2+1]) // 2 for i in range(n // 2)]
    elif n_ch != 1:
        raise ValueError(f"Unsupported channel count: {n_ch}")
    return samples, sr


def write_wav(path, samples, sample_rate=SAMPLE_RATE):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack(f"<{len(samples)}h", *samples))


def resample_linear(pcm, src_rate, dst_rate):
    if src_rate == dst_rate:
        return list(pcm)
    ratio = dst_rate / src_rate
    n_out = int(len(pcm) * ratio)
    out = [0] * n_out
    for i in range(n_out):
        pos = i / ratio
        idx = int(pos)
        frac = pos - idx
        a = pcm[idx] if idx < len(pcm) else 0
        b = pcm[idx + 1] if idx + 1 < len(pcm) else 0
        out[i] = int(a + (b - a) * frac)
    return out


# --- High-level ---------------------------------------------------------------

def wav_to_xa(wav_path, xa_path, channel=0):
    pcm, sr = read_wav(wav_path)
    if sr != SAMPLE_RATE:
        print(f"[wav_to_xa] resampling {sr} -> {SAMPLE_RATE}")
        pcm = resample_linear(pcm, sr, SAMPLE_RATE)
    xa = encode_xa(pcm, channel=channel)
    Path(xa_path).write_bytes(xa)
    return len(xa), len(pcm)


def xa_to_wav(xa_path, wav_path, channel=0):
    data = Path(xa_path).read_bytes()
    pcm = decode_xa(data, channel=channel)
    write_wav(wav_path, pcm)
    return len(data), len(pcm)


# --- CLI ----------------------------------------------------------------------

def cmd_decode(a):
    sz, n = xa_to_wav(a.input, a.output, channel=a.channel)
    print(f"Decoded {a.input} ({sz} B) -> {a.output} ({n} samples, {n/SAMPLE_RATE:.2f}s)")


def cmd_encode(a):
    sz, n = wav_to_xa(a.input, a.output, channel=a.channel)
    print(f"Encoded {a.input} ({n} samples, {n/SAMPLE_RATE:.2f}s) -> {a.output} "
          f"({sz} B, {sz//XA_FORM2_SECTOR} sectors)")


def cmd_test(a):
    """Roundtrip test on an XA file: decode -> encode -> decode.
    WARNING: SNR will be inf by construction (the encoder reproduces
    whatever it decoded). This only proves the codec is self-consistent.
    Use 'roundtrip' on a real WAV to test quality against fresh PCM."""
    data = Path(a.input).read_bytes()
    pcm1 = decode_xa(data, channel=a.channel)
    peak = max(abs(s) for s in pcm1) if pcm1 else 0
    rms  = (sum(s*s for s in pcm1) / len(pcm1)) ** 0.5 if pcm1 else 0
    print(f"Decoded:      {len(pcm1)} samples ({len(pcm1)/SAMPLE_RATE:.2f}s)")
    print(f"Peak:         {peak}")
    print(f"RMS:          {rms:.1f}")
    if peak < 100:
        print()
        print("WARNING: signal is SILENCE (peak < 100).")
        print("This is likely the wrong --channel. Try --channel 1 or 2.")
        return
    xa2 = encode_xa(pcm1, channel=a.channel)
    print(f"Re-encoded:   {len(xa2)} B ({len(xa2)//XA_FORM2_SECTOR} sectors)")
    pcm2 = decode_xa(xa2, channel=a.channel)
    print(f"Re-decoded:   {len(pcm2)} samples")
    n = min(len(pcm1), len(pcm2))
    sig = sum(pcm1[i]*pcm1[i] for i in range(n))
    noi = sum((pcm1[i]-pcm2[i])**2 for i in range(n))
    snr = float('inf') if noi == 0 else 10 * math.log10(sig / noi)
    print(f"SNR:          {snr:.2f} dB  (self-consistency, not quality)")
    print("OK (codec self-consistent)" if snr > 60 else "FAIL (encoder bug)")


def cmd_roundtrip(a):
    """Encode a WAV to XA, decode back to WAV, compare against the original.
    This is the real quality test."""
    pcm_in, sr = read_wav(a.input)
    if sr != SAMPLE_RATE:
        print(f"[roundtrip] resampling {sr} -> {SAMPLE_RATE}")
        pcm_in = resample_linear(pcm_in, sr, SAMPLE_RATE)
    print(f"Input WAV:    {len(pcm_in)} samples ({len(pcm_in)/SAMPLE_RATE:.2f}s) @ {sr} Hz")
    peak = max(abs(s) for s in pcm_in) if pcm_in else 0
    if peak < 100:
        print("ERROR: input WAV is silence")
        return
    xa = encode_xa(pcm_in, channel=0)
    print(f"XA encoded:   {len(xa)} B ({len(xa)//XA_FORM2_SECTOR} sectors)")
    pcm_out = decode_xa(xa, channel=0)
    print(f"XA decoded:   {len(pcm_out)} samples")
    n = min(len(pcm_in), len(pcm_out))
    sig = sum(pcm_in[i]*pcm_in[i] for i in range(n))
    noi = sum((pcm_in[i]-pcm_out[i])**2 for i in range(n))
    snr = float('inf') if noi == 0 else 10 * math.log10(sig / noi)
    print(f"SNR:          {snr:.2f} dB")
    write_wav(a.output, pcm_out)
    print(f"Wrote:        {a.output}")
    if snr >= 15:
        print("PASS — codec quality OK for PSX ADPCM")
    elif snr >= 8:
        print("MARGINAL — codec works but quality is low")
    else:
        print("FAIL — encoder bug likely")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("decode")
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--channel", type=int, default=0)
    p.set_defaults(func=cmd_decode)

    p = sub.add_parser("encode")
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--channel", type=int, default=0)
    p.set_defaults(func=cmd_encode)

    p = sub.add_parser("test")
    p.add_argument("input")
    p.add_argument("--channel", type=int, default=0)
    p.set_defaults(func=cmd_test)

    p = sub.add_parser("roundtrip")
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_roundtrip)

    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()