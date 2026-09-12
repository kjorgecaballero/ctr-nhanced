"""Validate a custom CTR vertex-animation compressor entirely in memory.

The script decodes authoritative Coco containers, checks decoded integer
coordinates against the previously extracted CSV evidence, re-encodes every
animation with a newly selected shared delta table, and requires byte-exact
vertex round-trips. It never creates or modifies a .ctr file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def align4(value: int) -> int:
    return (value + 3) & ~3


def read_container_data(path: Path) -> bytes:
    raw = path.read_bytes()
    if len(raw) < 4:
        raise ValueError(f"Container is too short: {path}")
    size = struct.unpack_from("<I", raw, 0)[0] & 0x7FFFFFFF
    if 4 + size > len(raw):
        raise ValueError(f"Invalid container data size in {path}")
    return raw[4 : 4 + size]


def i16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<h", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


class BitReader:
    def __init__(self, data: bytes):
        self.data = data
        self.bit_index = 0

    def read_signed(self, bit_count: int) -> int:
        value = 0
        for _ in range(bit_count):
            word_index = self.bit_index >> 5
            bit_in_word = self.bit_index & 31
            byte_offset = word_index * 4
            if byte_offset + 4 > len(self.data):
                raise EOFError("Compressed animation bitstream ended unexpectedly")
            word = struct.unpack_from("<I", self.data, byte_offset)[0]
            value = (value << 1) | ((word >> (31 - bit_in_word)) & 1)
            self.bit_index += 1
        sign_bit = 1 << (bit_count - 1)
        return value if not (value & sign_bit) else value - (1 << bit_count)


def parse_delta(raw: int) -> dict:
    return {
        "bits_x_field": (raw >> 6) & 7,
        "bits_y_field": (raw >> 3) & 7,
        "bits_z_field": raw & 7,
        "position_x_field": (raw >> 25) & 0x7F,
        "position_y_field": (raw >> 17) & 0xFF,
        "position_z_field": (raw >> 9) & 0xFF,
        "raw": raw,
    }


def pack_delta(delta: dict) -> int:
    return (
        ((int(delta["bits_x_field"]) & 7) << 6)
        | ((int(delta["bits_y_field"]) & 7) << 3)
        | (int(delta["bits_z_field"]) & 7)
        | ((int(delta["position_x_field"]) & 0x7F) << 25)
        | ((int(delta["position_y_field"]) & 0xFF) << 17)
        | ((int(delta["position_z_field"]) & 0xFF) << 9)
    )


def decode_frame_packed(deltas: list[dict], temporal: bytes) -> list[tuple[int, int, int]]:
    reader = BitReader(temporal)
    x_accumulator = 0
    y_accumulator = 0
    z_accumulator = 0
    points = []
    for delta in deltas:
        # The raw bitfields map high/middle/low to visible X/Y/Z. The existing
        # C# extractor appears to swap X/Z only because its compiled CtrDelta
        # properties expose those raw fields in reverse; direct binary parsing
        # must use the physical high-to-low mapping below.
        x_bits = delta["bits_x_field"]
        y_bits = delta["bits_y_field"]
        z_bits = delta["bits_z_field"]
        x_base = delta["position_x_field"] << 1
        y_base = delta["position_y_field"]
        z_base = delta["position_z_field"]
        # Retail MIPS branches around BOTH the base and previous accumulator
        # for an absolute 8-bit coordinate (8006a968/a9cc/aa2c).
        if x_bits == 7:
            x_accumulator = x_base = 0
        if y_bits == 7:
            y_accumulator = y_base = 0
        if z_bits == 7:
            z_accumulator = z_base = 0
        x_accumulator = (x_accumulator + x_base + reader.read_signed(x_bits + 1)) & 0xFF
        y_accumulator = (y_accumulator + y_base + reader.read_signed(y_bits + 1)) & 0xFF
        z_accumulator = (z_accumulator + z_base + reader.read_signed(z_bits + 1)) & 0xFF
        points.append((x_accumulator, y_accumulator, z_accumulator))
    return points


def signed_modular(value: int) -> int:
    return ((value + 128) & 0xFF) - 128


def choose_axis_delta(
    frames: list[list[tuple[int, int, int]]], vertex_index: int, axis: int
) -> tuple[int, int, list[int]]:
    if axis == 0:
        allowed_bases = set(range(0, 256, 2))
    elif axis == 1:
        allowed_bases = set(range(256))
    else:
        allowed_bases = set(range(256))

    targets = [frame[vertex_index][axis] for frame in frames]
    previous = [frame[vertex_index - 1][axis] if vertex_index else 0 for frame in frames]
    for bits in range(7):
        low = -(1 << bits)
        high = (1 << bits) - 1
        candidates = []
        first_difference = (targets[0] - previous[0]) & 0xFF
        candidate_bases = {
            (first_difference - temporal) & 0xFF for temporal in range(low, high + 1)
        } & allowed_bases
        for base in candidate_bases:
            temporal = [signed_modular(target - prior - base) for target, prior in zip(targets, previous)]
            if all(low <= value <= high for value in temporal):
                candidates.append((sum(abs(value) for value in temporal), base, temporal))
        if candidates:
            _, base, temporal = min(candidates)
            return bits, base, temporal

    # bits==7 is also a reset command, so the accumulator is zeroed before
    # this vertex in every frame. Eight signed temporal bits span all residues.
    # An absolute coordinate has no base, even if unused header bits are set.
    return 7, 0, [signed_modular(target) for target in targets]


def encode_bits(values: list[tuple[int, int]]) -> bytes:
    bits = []
    for value, bit_count in values:
        encoded = value & ((1 << bit_count) - 1)
        bits.extend((encoded >> shift) & 1 for shift in range(bit_count - 1, -1, -1))
    while len(bits) % 32:
        bits.append(0)
    output = bytearray()
    for first in range(0, len(bits), 32):
        word = 0
        for bit_index, bit in enumerate(bits[first : first + 32]):
            word |= bit << (31 - bit_index)
        output.extend(struct.pack("<I", word))
    return bytes(output)


def encode_animation(frames: list[list[tuple[int, int, int]]]) -> tuple[list[dict], list[bytes], dict]:
    if not frames or not frames[0]:
        raise ValueError("Cannot encode an empty animation")
    vertex_count = len(frames[0])
    if any(len(frame) != vertex_count for frame in frames):
        raise ValueError("Animation frames have inconsistent vertex counts")

    deltas = []
    temporal_by_frame: list[list[tuple[int, int]]] = [[] for _ in frames]
    bit_histogram = {str(bits): 0 for bits in range(8)}
    for vertex_index in range(vertex_count):
        x_bits, x_base, x_temporal = choose_axis_delta(frames, vertex_index, 0)
        y_bits, y_base, y_temporal = choose_axis_delta(frames, vertex_index, 1)
        z_bits, z_base, z_temporal = choose_axis_delta(frames, vertex_index, 2)
        delta = {
            "bits_x_field": x_bits,
            "bits_y_field": y_bits,
            "bits_z_field": z_bits,
            "position_x_field": x_base // 2,
            "position_y_field": y_base,
            "position_z_field": z_base,
        }
        raw = pack_delta(delta)
        parsed = parse_delta(raw)
        if pack_delta(parsed) != raw:
            raise AssertionError("Delta pack/unpack mismatch")
        deltas.append(parsed)
        for bits in (x_bits, y_bits, z_bits):
            bit_histogram[str(bits)] += 1
        for frame_index in range(len(frames)):
            temporal_by_frame[frame_index].extend(
                (
                    (x_temporal[frame_index], x_bits + 1),
                    (y_temporal[frame_index], y_bits + 1),
                    (z_temporal[frame_index], z_bits + 1),
                )
            )

    encoded_frames = [encode_bits(values) for values in temporal_by_frame]
    if len({len(value) for value in encoded_frames}) != 1:
        raise AssertionError("Shared deltas must produce equal frame stream lengths")
    stats = {
        "vertex_count": vertex_count,
        "frame_count": len(frames),
        "delta_table_bytes": vertex_count * 4,
        "temporal_bits_per_frame": sum(bit_count for _, bit_count in temporal_by_frame[0]),
        "temporal_bytes_per_frame_aligned32bits": len(encoded_frames[0]),
        "bit_histogram_per_axis": bit_histogram,
    }
    return deltas, encoded_frames, stats


def csv_expectations(inventory: dict) -> dict[tuple[str, str, int], Path]:
    result = {}
    for tier in inventory["tiers"].values():
        source = str(Path(tier["source"]["path"]).resolve()).lower()
        for animation in tier["animations"]:
            result[(source, animation["mesh"], int(animation["animation_index"]))] = Path(
                animation["output_csv"]
            )
    return result


def load_csv_raw(path: Path, frame_count: int, vertex_count: int) -> list[list[tuple[int, int, int]]]:
    frames = [[None] * vertex_count for _ in range(frame_count)]
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            frame_index = int(row["frame"])
            vertex_index = int(row["vertex"])
            frames[frame_index][vertex_index] = (
                int(row["raw_x"]),
                int(row["raw_y"]),
                int(row["raw_z"]),
            )
    if any(value is None for frame in frames for value in frame):
        raise ValueError(f"Incomplete CSV extraction: {path}")
    return frames


def build_text_report(report: dict) -> str:
    lines = [
        "CTR ANIMATION COMPRESSOR VALIDATION - IN MEMORY ONLY",
        "====================================================",
        "",
        f"Generated UTC: {report['generated_utc']}",
        f"Status: {report['status']}",
        f"Source containers: {report['source_count']}",
        f"Animations checked: {report['animation_count']}",
        f"Stored frames checked: {report['stored_frame_count']}",
        f"Decoded vertices checked: {report['decoded_vertex_count']}",
        "CTR files written: no",
        "",
        "Checks",
        "------",
        f"Runtime-offset decoder matches CSV where CSV is authoritative: {report['checks']['runtime_csv_matches_where_applicable']}",
        f"Legacy non-0x1C CSV discrepancy fully explained: {report['checks']['legacy_csv_discrepancies_accounted_for']}",
        f"Custom encode/decode is byte-exact: {report['checks']['custom_roundtrip_exact']}",
        f"Source hashes stable: {report['checks']['source_hashes_stable']}",
        f"All sources remain compressed: {report['checks']['all_sources_compressed']}",
        "",
        "Per animation",
        "-------------",
    ]
    for source in report["sources"]:
        lines.append(f"{source['source_key']}: {source['path']}")
        for animation in source["animations"]:
            lines.append(
                f"  {animation['mesh']} / {animation['animation']}: "
                f"frames={animation['frames']} vertices={animation['vertices']} "
                f"originalFrame={animation['original_frame_size']} "
                f"reencodedFrame={animation['projected_frame_size']} "
                f"roundtrip={animation['roundtrip_exact']} runtimeCsv={animation['csv_match']} "
                f"legacy0x1C={animation['legacy_0x1c_csv_match']}"
            )
        lines.append("")
    lines.extend(
        [
            "Boundary",
            "--------",
            "This validates the compression algorithm on Coco's existing vertices only.",
            "It does not propagate V36 geometry and does not create an animated output model.",
            "V36 propagation remains gated by explicit visual approval.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serialization-plan", required=True, type=Path)
    parser.add_argument("--animation-inventory", required=True, type=Path)
    parser.add_argument("--json-out", required=True, type=Path)
    parser.add_argument("--text-out", required=True, type=Path)
    args = parser.parse_args()
    for output in (args.json_out, args.text_out):
        if output.suffix.lower() == ".ctr":
            raise SystemExit("Safety guard: compressor validation cannot write a .ctr file")

    plan = json.loads(args.serialization_plan.read_text(encoding="utf-8"))
    inventory = json.loads(args.animation_inventory.read_text(encoding="utf-8"))
    csv_map = csv_expectations(inventory)
    total_animations = 0
    total_frames = 0
    total_vertices = 0
    all_runtime_csv_where_applicable = True
    all_csv_discrepancies_accounted = True
    all_roundtrip = True
    all_hashes = True
    all_compressed = True
    source_reports = []

    for source in plan["sources"]:
        path = Path(source["path"])
        before_hash = sha256(path)
        data = read_container_data(path)
        animation_reports = []
        for mesh in source["model"]["meshes"]:
            vertex_count = int(mesh["native_vertex_count"])
            for animation in mesh["animations"]:
                total_animations += 1
                frame_count = int(animation["stored_frame_count"])
                total_frames += frame_count
                total_vertices += frame_count * vertex_count
                compressed = bool(animation["compressed"])
                all_compressed = all_compressed and compressed
                if not compressed:
                    raise RuntimeError(f"Unexpected raw source animation: {path} {animation['name']}")
                delta_offset = int(animation["delta_range"][0])
                deltas = [parse_delta(u32(data, delta_offset + index * 4)) for index in range(vertex_count)]
                packed_frames = []
                raw_frames = []
                legacy_raw_frames = []
                vertex_offsets = []
                for frame in animation["frames"]:
                    frame_offset = int(frame["range"][0])
                    frame_end = int(frame["range"][1])
                    stream_offset = int(frame["vertex_stream_absolute_offset"])
                    vertex_offsets.append(int(frame["vertex_stream_relative_offset"]))
                    packed = decode_frame_packed(deltas, data[stream_offset:frame_end])
                    packed_frames.append(packed)
                    offset = (i16(data, frame_offset), i16(data, frame_offset + 2), i16(data, frame_offset + 4))
                    raw_frames.append(
                        [
                            (offset[0] + point[0], offset[1] + point[1], offset[2] + point[2])
                            for point in packed
                        ]
                    )
                    legacy_packed = decode_frame_packed(deltas, data[frame_offset + 28 : frame_end])
                    legacy_raw_frames.append(
                        [
                            (offset[0] + point[0], offset[1] + point[1], offset[2] + point[2])
                            for point in legacy_packed
                        ]
                    )

                source_resolved = str(path.resolve()).lower()
                csv_path = csv_map.get((source_resolved, mesh["name"], int(animation["animation_index"])))
                csv_match = None
                legacy_0x1c_csv_match = None
                first_csv_mismatch = None
                if csv_path is not None:
                    expected = load_csv_raw(csv_path, frame_count, vertex_count)
                    csv_match = expected == raw_frames
                    legacy_0x1c_csv_match = expected == legacy_raw_frames
                    if not csv_match:
                        for frame_index, (expected_frame, actual_frame) in enumerate(zip(expected, raw_frames)):
                            for vertex_index, (expected_point, actual_point) in enumerate(
                                zip(expected_frame, actual_frame)
                            ):
                                if expected_point != actual_point:
                                    first_csv_mismatch = {
                                        "frame": frame_index,
                                        "vertex": vertex_index,
                                        "expected": expected_point,
                                        "actual": actual_point,
                                        "packed": packed_frames[frame_index][vertex_index],
                                        "frame_offset": [
                                            i16(data, int(animation["frames"][frame_index]["range"][0])),
                                            i16(data, int(animation["frames"][frame_index]["range"][0]) + 2),
                                            i16(data, int(animation["frames"][frame_index]["range"][0]) + 4),
                                        ],
                                    }
                                    break
                            if first_csv_mismatch is not None:
                                break
                    nonstandard_offset = any(value != 28 for value in vertex_offsets)
                    if not nonstandard_offset:
                        all_runtime_csv_where_applicable = all_runtime_csv_where_applicable and csv_match
                    accounted = bool(csv_match or (nonstandard_offset and legacy_0x1c_csv_match))
                    all_csv_discrepancies_accounted = all_csv_discrepancies_accounted and accounted

                encoded_deltas, encoded_frames, stats = encode_animation(packed_frames)
                decoded_roundtrip = [
                    decode_frame_packed(encoded_deltas, encoded) for encoded in encoded_frames
                ]
                roundtrip_exact = decoded_roundtrip == packed_frames
                all_roundtrip = all_roundtrip and roundtrip_exact
                pointer_offset = max(vertex_offsets)
                projected_frame_size = align4(pointer_offset + stats["temporal_bytes_per_frame_aligned32bits"])
                animation_reports.append(
                    {
                        "mesh": mesh["name"],
                        "animation": animation["name"],
                        "animation_index": animation["animation_index"],
                        "frames": frame_count,
                        "vertices": vertex_count,
                        "original_frame_size": animation["frame_size"],
                        "original_vertex_stream_offsets": sorted(set(vertex_offsets)),
                        "reencoded_delta_table_bytes": stats["delta_table_bytes"],
                        "reencoded_temporal_bits_per_frame": stats["temporal_bits_per_frame"],
                        "reencoded_temporal_bytes_per_frame": stats[
                            "temporal_bytes_per_frame_aligned32bits"
                        ],
                        "projected_frame_size": projected_frame_size,
                        "projected_frame_size_delta": projected_frame_size - int(animation["frame_size"]),
                        "bit_histogram_per_axis": stats["bit_histogram_per_axis"],
                        "roundtrip_exact": roundtrip_exact,
                        "csv_path": str(csv_path) if csv_path else None,
                        "csv_match": csv_match,
                        "legacy_0x1c_csv_match": legacy_0x1c_csv_match,
                        "runtime_vertex_offset_discrepancy": bool(
                            csv_path is not None
                            and not csv_match
                            and legacy_0x1c_csv_match
                            and any(value != 28 for value in vertex_offsets)
                        ),
                        "first_csv_mismatch": first_csv_mismatch,
                    }
                )
        after_hash = sha256(path)
        hash_stable = before_hash == after_hash == source["sha256_before"]
        all_hashes = all_hashes and hash_stable
        source_reports.append(
            {
                "source_key": source["source_key"],
                "path": str(path),
                "sha256_before": before_hash,
                "sha256_after": after_hash,
                "hash_stable": hash_stable,
                "animations": animation_reports,
            }
        )

    checks = {
        "runtime_csv_matches_where_applicable": all_runtime_csv_where_applicable,
        "legacy_csv_discrepancies_accounted_for": all_csv_discrepancies_accounted,
        "custom_roundtrip_exact": all_roundtrip,
        "source_hashes_stable": all_hashes,
        "all_sources_compressed": all_compressed,
    }
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "In-memory CTR animation compression validation; no V36 propagation and no CTR writes",
        "serialization_plan": str(args.serialization_plan.resolve()),
        "animation_inventory": str(args.animation_inventory.resolve()),
        "source_count": len(source_reports),
        "animation_count": total_animations,
        "stored_frame_count": total_frames,
        "decoded_vertex_count": total_vertices,
        "sources": source_reports,
        "checks": checks,
        "writes_ctr_files": False,
        "status": "PASS" if all(checks.values()) else "FAIL",
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.text_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    args.text_out.write_text(build_text_report(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "sources": report["source_count"],
                "animations": total_animations,
                "frames": total_frames,
                "vertices": total_vertices,
                "writes_ctr_files": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
