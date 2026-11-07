"""Virtual MP4 muxer: video + audio DASH files -> one MP4 with an exact size and Range support,
served instantly without downloading anything first.

YouTube (and other DASH sources) ship video and audio as separate *fragmented* MP4 files:

    ftyp | moov | sidx (index: size + duration of every segment) | moof mdat | moof mdat | ...

Segments use "default-base-is-moof" addressing, so they can be moved anywhere in a file.
From the first few KB of each file we know the exact layout of a combined file:

    ftyp | moov (video trak + audio trak) | segments of both tracks, interleaved by time

Every output byte maps to a byte of one of the inputs, except 8 bytes per segment that we
patch (track id of audio fragments, fragment sequence numbers). So any byte range of the
combined file can be produced on demand: browsers and IDM get Content-Length, resume and
multi-connection downloads, and the download starts the moment the user clicks.
"""

from __future__ import annotations

import asyncio
import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from .extractor import Item, Resolved
from .stream import StreamError, _open_with_refresh

PROBE = 256 * 1024          # bytes read from the start of each input to find ftyp/moov/sidx
MAX_REQ = 8 * 1024 * 1024   # largest single upstream request (YouTube throttles bigger ones)
READ = 256 * 1024


class NotMuxable(Exception):
    """Inputs aren't fragmented MP4 with a segment index: caller falls back to ffmpeg."""


# ---------------------------------------------------------------- box helpers


def _boxes(buf: bytes, start: int, end: int):
    off = start
    while off + 8 <= end:
        size, typ = struct.unpack_from(">I4s", buf, off)
        hdr = 8
        if size == 1:
            size = struct.unpack_from(">Q", buf, off + 8)[0]
            hdr = 16
        elif size == 0:
            size = end - off
        if size < hdr:
            raise NotMuxable("bad box")
        yield typ.decode("latin1"), off, size, hdr
        off += size


def _child(buf: bytes, start: int, end: int, typ: str) -> tuple[int, int, int]:
    for t, off, size, hdr in _boxes(buf, start, end):
        if t == typ:
            return off, size, hdr
    raise NotMuxable(f"missing {typ}")


@dataclass
class Segment:
    track: int          # 0 = video, 1 = audio
    src_off: int
    size: int
    start: float        # seconds


@dataclass
class Track:
    format_id: str
    total: int
    ftyp: bytes
    moov: bytes
    segments: list[Segment]


def parse_track(buf: bytes, total: int, format_id: str, track: int) -> Track:
    top = {t: (off, size, hdr) for t, off, size, hdr in _boxes(buf, 0, min(len(buf), 4096 * 64))
           if t in ("ftyp", "moov", "sidx") or t == "moof"}
    if not {"ftyp", "moov", "sidx"} <= top.keys():
        raise NotMuxable("not a fragmented MP4 with sidx")
    f_off, f_size, _ = top["ftyp"]
    m_off, m_size, _ = top["moov"]
    s_off, s_size, _ = top["sidx"]
    if s_off + s_size > len(buf):
        raise NotMuxable("sidx larger than probe")

    p = s_off + 8
    version = buf[p]
    p += 4
    _ref_id, timescale = struct.unpack_from(">II", buf, p)
    p += 8
    if version == 0:
        ept, first = struct.unpack_from(">II", buf, p)
        p += 8
    else:
        ept, first = struct.unpack_from(">QQ", buf, p)
        p += 16
    _, count = struct.unpack_from(">HH", buf, p)
    p += 4

    segs: list[Segment] = []
    off = s_off + s_size + first
    t = ept
    for i in range(count):
        ref, dur, _sap = struct.unpack_from(">III", buf, p + 12 * i)
        if ref >> 31:
            raise NotMuxable("nested sidx")
        size = ref & 0x7FFFFFFF
        segs.append(Segment(track, off, size, t / timescale))
        off += size
        t += dur
    if off != total:
        raise NotMuxable("sidx does not cover the file")

    # Check the fragment layout we patch: moof > mfhd(16) > traf > tfhd, one moof+mdat per segment.
    m0 = segs[0].src_off
    if m0 + 48 > len(buf):
        raise NotMuxable("first fragment not in probe")
    if (buf[m0 + 4:m0 + 8], buf[m0 + 12:m0 + 16], buf[m0 + 28:m0 + 32], buf[m0 + 36:m0 + 40]) != (b"moof", b"mfhd", b"traf", b"tfhd"):
        raise NotMuxable("unexpected fragment layout")
    tfhd_flags = int.from_bytes(buf[m0 + 41:m0 + 44], "big")
    if tfhd_flags & 0x1:   # explicit base-data-offset = absolute file positions -> not relocatable
        raise NotMuxable("fragments not relocatable")
    moof_size = struct.unpack_from(">I", buf, m0)[0]
    if m0 + moof_size + 8 <= len(buf):
        mdat_size, mdat = struct.unpack_from(">I4s", buf, m0 + moof_size)
        if mdat != b"mdat" or moof_size + mdat_size != segs[0].size:
            raise NotMuxable("segment is not exactly moof+mdat")

    return Track(format_id, total, buf[f_off:f_off + f_size], buf[m_off:m_off + m_size], segs)


def _set_u32(b: bytearray, pos: int, value: int) -> None:
    struct.pack_into(">I", b, pos, value)


def build_moov(v_moov: bytes, a_moov: bytes) -> bytes:
    """moov with the video track (id 1) and the audio track renumbered to id 2."""
    v_mvhd = v_mvex = v_trak = a_mvex = a_trak = None
    for t, off, size, hdr in _boxes(v_moov, 8, len(v_moov)):
        if t == "mvhd":
            v_mvhd = bytearray(v_moov[off:off + size])
        elif t == "mvex":
            v_mvex = (off, size, hdr)
        elif t == "trak":
            v_trak = v_moov[off:off + size]
    for t, off, size, hdr in _boxes(a_moov, 8, len(a_moov)):
        if t == "mvex":
            a_mvex = (off, size, hdr)
        elif t == "trak":
            a_trak = bytearray(a_moov[off:off + size])
    if not (v_mvhd and v_mvex and v_trak and a_mvex and a_trak):
        raise NotMuxable("incomplete moov")

    _set_u32(v_mvhd, len(v_mvhd) - 4, 3)   # next_track_ID

    v_trex_off, v_trex_size, _ = _child(v_moov, v_mvex[0] + v_mvex[2], v_mvex[0] + v_mvex[1], "trex")
    a_trex_off, a_trex_size, _ = _child(a_moov, a_mvex[0] + a_mvex[2], a_mvex[0] + a_mvex[1], "trex")
    v_trex = v_moov[v_trex_off:v_trex_off + v_trex_size]
    a_trex = bytearray(a_moov[a_trex_off:a_trex_off + a_trex_size])
    _set_u32(a_trex, 12, 2)
    mvex = struct.pack(">I4s", 8 + len(v_trex) + len(a_trex), b"mvex") + v_trex + bytes(a_trex)

    tk_off, _, _ = _child(bytes(a_trak), 8, len(a_trak), "tkhd")
    _set_u32(a_trak, tk_off + (28 if a_trak[tk_off + 8] == 1 else 20), 2)

    body = bytes(v_mvhd) + mvex + v_trak + bytes(a_trak)
    return struct.pack(">I4s", 8 + len(body), b"moov") + body


# ---------------------------------------------------------------- layout


@dataclass
class Run:
    """A contiguous slice of one input, placed at out_off in the output."""
    out_off: int
    track: int
    src_off: int
    size: int
    patches: list[tuple[int, bytes]] = field(default_factory=list)   # (offset in run, 4 bytes)


@dataclass
class VirtualMp4:
    header: bytes
    runs: list[Run]
    total: int
    format_ids: tuple[str, str]


def plan(video: Track, audio: Track) -> VirtualMp4:
    header = video.ftyp + build_moov(video.moov, audio.moov)
    segs = sorted(video.segments + audio.segments, key=lambda s: (s.start, s.track))
    runs: list[Run] = []
    out = len(header)
    for seq, s in enumerate(segs, start=1):
        patches = [(20, struct.pack(">I", seq))]                 # mfhd.sequence_number
        if s.track == 1:
            patches.append((44, struct.pack(">I", 2)))           # tfhd.track_ID of audio
        last = runs[-1] if runs else None
        if last and last.track == s.track and last.src_off + last.size == s.src_off and last.size + s.size <= MAX_REQ:
            patches = [(last.size + p, b) for p, b in patches]
            last.size += s.size
            last.patches += patches
        else:
            runs.append(Run(out, s.track, s.src_off, s.size, patches))
        out += s.size
    return VirtualMp4(header, runs, out, (video.format_id, audio.format_id))


async def build(resolved: Resolved, item: Item, video_id: str, audio_id: str) -> VirtualMp4:
    tracks = []
    for n, fid in enumerate((video_id, audio_id)):
        f = item.format(fid)
        if f is None or f.get("ext") not in ("mp4", "m4a") or f.get("protocol") not in ("https", "http"):
            raise NotMuxable("not an MP4 DASH file")
        _, resp = await asyncio.to_thread(_open_with_refresh, resolved, item, fid, f"bytes=0-{PROBE - 1}")
        try:
            buf = await asyncio.to_thread(resp.read)
            cr = resp.headers.get("Content-Range", "")
        finally:
            resp.close()
        total = f.get("filesize") or (int(cr.rsplit("/", 1)[-1]) if cr.rsplit("/", 1)[-1].isdigit() else None)
        if not total or resp.status != 206:
            raise NotMuxable("no range support")
        tracks.append(parse_track(buf, total, fid, n))
    return plan(*tracks)


# ---------------------------------------------------------------- serving


def _fetch_plan(vm: VirtualMp4, start: int, end: int) -> list[tuple[int, int, int, list[tuple[int, bytes]]]]:
    """Upstream reads needed for output bytes [start, end]: (track, src_from, src_to, patches rel. to src_from)."""
    reqs = []
    for r in vm.runs:
        r_end = r.out_off + r.size - 1
        if r_end < start or r.out_off > end:
            continue
        a = max(start, r.out_off) - r.out_off
        b = min(end, r_end) - r.out_off
        reqs.append((r.track, r.src_off + a, r.src_off + b, [(p - a, v) for p, v in r.patches]))
    return reqs


async def stream_range(resolved: Resolved, item: Item, vm: VirtualMp4, start: int, end: int) -> AsyncIterator[bytes]:
    if start < len(vm.header):
        yield vm.header[start:min(end + 1, len(vm.header))]
        start = len(vm.header)
    if start > end:
        return
    reqs = _fetch_plan(vm, start, end)

    def opener(req):
        track, a, b, _ = req
        return _open_with_refresh(resolved, item, vm.format_ids[track], f"bytes={a}-{b}")[1]

    # Open the next upstream request while the current one is being sent: hides latency.
    pending = asyncio.ensure_future(asyncio.to_thread(opener, reqs[0])) if reqs else None
    try:
        for i, req in enumerate(reqs):
            resp = await pending
            pending = asyncio.ensure_future(asyncio.to_thread(opener, reqs[i + 1])) if i + 1 < len(reqs) else None
            _, a, b, patches = req
            pos = 0
            try:
                while pos <= b - a:
                    chunk = await asyncio.to_thread(resp.read, min(READ, b - a + 1 - pos))
                    if not chunk:
                        raise StreamError("The platform closed the connection early.")
                    buf = None
                    for p, v in patches:   # 4-byte patches that fall inside this chunk
                        for k in range(4):
                            q = p + k - pos
                            if 0 <= q < len(chunk):
                                buf = buf or bytearray(chunk)
                                buf[q] = v[k]
                    yield bytes(buf) if buf is not None else chunk
                    pos += len(chunk)
            finally:
                await asyncio.to_thread(resp.close)
    finally:
        if pending is not None:
            pending.cancel()
