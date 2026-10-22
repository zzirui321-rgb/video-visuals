"""Read SRT and validate video-visuals manifests. Never writes or edits assets."""
import argparse
import json
import math
import re
import sys
import shutil
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

STAMP = r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})"


def milliseconds(groups):
    h, m, s, ms = map(int, groups)
    if m >= 60 or s >= 60:
        raise ValueError("Invalid SRT clock")
    return ((h * 60 + m) * 60 + s) * 1000 + ms


def read_srt(path):
    content = Path(path).read_text(encoding="utf-8-sig").strip()
    cues = []
    ids = set()
    for block in re.split(r"\n\s*\n", content):
        lines = block.strip().splitlines()
        if not lines:
            continue
        if len(lines) < 3:
            raise ValueError("Incomplete SRT block")
        cue_id = lines[0].strip()
        match = re.fullmatch(STAMP + r"\s*-->\s*" + STAMP + r"(?:\s+.*)?", lines[1].strip())
        if not cue_id.isdigit() or cue_id in ids or not match:
            raise ValueError(f"Invalid or duplicate SRT cue: {cue_id}")
        start, end = milliseconds(match.groups()[:4]), milliseconds(match.groups()[4:])
        if end <= start or (cues and start < cues[-1]["start_ms"]):
            raise ValueError(f"Invalid SRT interval/order: {cue_id}")
        ids.add(cue_id)
        cues.append(dict(id=cue_id, start_ms=start, end_ms=end, text="\n".join(lines[2:])))
    if not cues:
        raise ValueError("SRT has no cues")
    return {"duration_ms": max(c["end_ms"] for c in cues), "cues": cues}


def integer(value):
    return type(value) is int


def prefix(ms):
    seconds, milli = divmod(ms, 1000)
    minutes, second = divmod(seconds, 60)
    hour, minute = divmod(minutes, 60)
    return f"{hour:02d}-{minute:02d}-{second:02d}-{milli:03d}_"


def probe_video(path, executable=None):
    tool = executable or shutil.which('ffprobe')
    if not tool:
        raise ValueError('Video verification requires ffprobe (PATH or manifest ffprobe_path)')
    result = subprocess.run([str(tool), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], capture_output=True, text=True, check=True, timeout=30)
    probe = json.loads(result.stdout)
    stream = next((s for s in probe.get('streams', []) if s.get('codec_type') == 'video'), None)
    if not stream:
        raise ValueError('No video stream')
    seconds = float(stream.get('duration') or probe.get('format', {}).get('duration', 0))
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('No valid measured video duration')
    return int(stream['width']), int(stream['height']), round(seconds * 1000)


def check(manifest):
    from PIL import Image
    manifest = Path(manifest).resolve()
    data = json.loads(manifest.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Manifest must be an object")
    errors, measured, timed = [], [], []
    def fail(message):
        errors.append(message)
    def local(value):
        if not isinstance(value, str) or not value:
            raise ValueError("Missing file path")
        p = (manifest.parent / value).resolve()
        if not p.is_relative_to(manifest.parent):
            raise ValueError("Asset path must stay inside output folder")
        return p
    requested = data.get("requested")
    if not isinstance(requested, list) or not requested or any(k not in ("cover", "chapter", "broll") for k in requested):
        raise ValueError("requested must list cover/chapter/broll")
    assets = data.get("assets")
    if not isinstance(assets, list):
        raise ValueError("assets must be a list")
    cues, duration = {}, data.get("duration_ms")
    if any(k in requested for k in ("chapter", "broll")):
        if not data.get("srt_path"):
            fail("Timeline requires srt_path")
        else:
            parsed = read_srt(manifest.parent / data["srt_path"])
            cues = {c["id"]: c for c in parsed["cues"]}
            if duration is None:
                duration = parsed["duration_ms"]
            elif not integer(duration) or duration < parsed["duration_ms"]:
                fail("duration_ms must cover the last subtitle")
        if not integer(duration) or duration <= 0:
            fail("Timeline requires positive integer duration_ms")
            duration = 0
    ids, paths, kinds, covers = set(), set(), set(), []
    for number, asset in enumerate(assets):
        if not isinstance(asset, dict):
            fail(f"Asset {number}: must be an object")
            continue
        label = str(asset.get("id", f"#{number}"))
        kind = asset.get("kind")
        if not isinstance(asset.get("id"), str) or not asset["id"] or label in ids:
            fail(f"{label}: missing/duplicate id")
        ids.add(label)
        if kind not in requested:
            fail(f"{label}: unrequested/invalid kind")
        if isinstance(kind, str):
            kinds.add(kind)
        if asset.get("status") != "approved" or asset.get("visual_checked") is not True:
            fail(f"{label}: not visually approved")
        if not asset.get("prompt_ref") or not asset.get("source"):
            fail(f"{label}: missing prompt/source record")
        if kind == "cover":
            covers.append(asset.get("ratio"))
            if asset.get("preview_checked") is not True:
                fail(f"{label}: missing small-preview check")
        try:
            path = local(asset.get("path"))
            pathkey = str(path).casefold()
            if pathkey in paths and not (kind == 'broll' and asset.get('media_type') == 'video'):
                fail(f"{label}: duplicate path")
            paths.add(pathkey)
            is_video = asset.get('media_type') == 'video'
            if is_video:
                if kind != 'broll':
                    fail(f'{label}: video only allowed for B-roll')
                if not path.is_file() or path.stat().st_size == 0:
                    raise ValueError('Missing/empty video')
                w, h, length = probe_video(path, data.get('ffprobe_path'))
                if asset.get('duration_ms') != length:
                    fail(f'{label}: declared video duration differs from measured {length}ms')
                si, so = asset.get('source_in_ms'), asset.get('source_out_ms')
                if not integer(si) or not integer(so) or not 0 <= si < so <= length:
                    fail(f'{label}: invalid source video interval')
                else:
                    speed = asset.get('playback_speed', 1)
                    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed) or speed <= 0:
                        fail(f'{label}: invalid playback speed')
                    elif integer(asset.get('end_ms')) and integer(asset.get('start_ms')) and abs((so-si)/speed-(asset['end_ms']-asset['start_ms'])) > 100:
                        fail(f'{label}: source clip duration does not match target interval')
            else:
                if kind != 'broll' and path.suffix.lower() != '.png':
                    fail(f'{label}: delivery must be PNG')
                with Image.open(path) as im:
                    im.load()
                    w, h = im.size
                    if kind != 'broll' and im.format != 'PNG':
                        fail(f'{label}: file content is not PNG')
            measured.append({"id": label, "width": w, "height": h})
            if asset.get("width") != w or asset.get("height") != h:
                fail(f"{label}: declared dimensions differ from actual {w}x{h}")
            ratio = asset.get("ratio", "16:9")
            if not isinstance(ratio, str) or not re.fullmatch(r"[1-9]\d*:[1-9]\d*", ratio):
                raise ValueError("Invalid ratio")
            rw, rh = map(int, ratio.split(":"))
            if not math.isclose(w / h, rw / rh, rel_tol=0.005):
                fail(f"{label}: actual aspect ratio differs from {ratio}")
            if kind in ("chapter", "broll") and integer(asset.get("start_ms")):
                expected = prefix(asset["start_ms"]) + ("Broll_" if kind == "broll" else "章节")
                if not path.name.startswith(expected) and not (is_video and asset.get('shared_source') is True):
                    fail(f"{label}: filename does not match time/type")
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError, Image.DecompressionBombError) as exc:
            fail(f"{label}: image check failed: {exc}")
        if asset.get('origin') == 'web':
            for field in ('source_page', 'license', 'license_url', 'credit_text', 'accessed_at'):
                if not isinstance(asset.get(field), str) or not asset[field].strip():
                    fail(f'{label}: missing web provenance {field}')
            if asset.get('usage_status') != 'cleared':
                fail(f'{label}: web usage conditions not verified')
        if kind == "chapter":
            try:
                editable = local(asset.get("editable_path"))
                if editable.suffix.lower() != ".svg":
                    raise ValueError("Chapter source must be SVG")
                root = ET.parse(editable).getroot()
                if not any(el.tag.split("}")[-1] == "text" and "".join(el.itertext()).strip() for el in root.iter()):
                    raise ValueError("SVG has no editable text")
            except (OSError, ValueError, ET.ParseError) as exc:
                fail(f"{label}: editable source failed: {exc}")
        if kind in ("chapter", "broll"):
            start, end = asset.get("start_ms"), asset.get("end_ms")
            if not integer(start) or not integer(end) or start < 0 or end <= start:
                fail(f"{label}: invalid timeline interval")
                continue
            if integer(duration) and end > duration:
                fail(f"{label}: exceeds video duration")
            refs = asset.get("source_cues")
            if not isinstance(refs, list) or not refs or any(not isinstance(c, str) or c not in cues for c in refs):
                fail(f"{label}: missing/unknown source cues")
            elif not any(cues[c]["start_ms"] < end and cues[c]["end_ms"] > start for c in refs):
                fail(f"{label}: source cues do not overlap display interval")
            timed.append((start, end, kind, label))
    for kind in requested:
        if kind not in kinds:
            fail(f"Missing requested asset type: {kind}")
    if "cover" in requested:
        ratios = data.get("cover_ratios", ["16:9", "4:3"])
        if not isinstance(ratios, list) or not ratios or any(not isinstance(r, str) for r in ratios):
            fail("Invalid cover_ratios")
        elif sorted(covers, key=str) != sorted(ratios):
            fail("Cover ratio deliveries do not match requested ratios")
    timed.sort()
    for i, item in enumerate(timed):
        for previous in timed[:i]:
            if previous[1] > item[0]:
                fail(f"Overlap: {previous[3]} / {item[3]}")
    chapters = [t[0] for t in timed if t[2] == "chapter"]
    for start, end, kind, label in timed:
        if kind == "broll" and any(start < c < end for c in chapters):
            fail(f"{label}: crosses chapter boundary")
    limit = data.get("broll_limit", 2)
    if not integer(limit) or limit < 1:
        fail("broll_limit must be a positive integer")
    else:
        starts = [t[0] for t in timed if t[2] == "broll"]
        for i in range(len(starts) - limit):
            if starts[i + limit] - starts[i] < 60000:
                fail(f"B-roll density exceeds {limit} in a rolling 60 seconds at {starts[i]}ms")
    return {"ok": not errors, "errors": errors, "measured": measured, "asset_count": len(assets)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("srt", "check"))
    parser.add_argument("path")
    args = parser.parse_args()
    try:
        result = read_srt(args.path) if args.command == "srt" else check(args.path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok", True) else 1
    except (OSError, ValueError, TypeError, ImportError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
