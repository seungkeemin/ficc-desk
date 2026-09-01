"""실행 아이콘(scripts/ficc.ico)을 만든다.

의존성을 늘리지 않으려고 PNG 와 ICO 를 손으로 쓴다 — Pillow 를 넣을 이유가
아이콘 하나뿐이면 1 년 뒤 설치가 안 되는 쪽이 더 비싸다 (CLAUDE.md: 표준 라이브러리 우선).

바이너리를 저장소에 두면서 어떻게 만들었는지 모르는 상태를 만들지 않으려고
생성기를 함께 남긴다. 다시 만들려면:

  .venv\\Scripts\\python scripts\\make_icon.py

그림은 화면의 시각 언어를 그대로 쓴다 — 배경 #0E1013, 왼쪽 앰버 바(무효화 워치
패널의 3px 바), 블로터 행 세 줄. 모서리 반경 0, 그림자 없음, 그라디언트 없음.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

BG = (0x0E, 0x10, 0x13, 255)      # --bg
FG = (0xD7, 0xDB, 0xE0, 255)      # --fg
DIM = (0x8A, 0x91, 0x99, 255)     # --fg-dim
ACCENT = (0xFF, 0x9A, 0x1F, 255)  # --accent

SIZES = (16, 32, 48, 64, 128, 256)

# (x0, x1, y0, y1, 색) — 전부 아이콘 한 변에 대한 비율이다.
SHAPES = (
    (0.000, 0.125, 0.000, 1.000, ACCENT),   # 좌측 앰버 바
    (0.250, 0.875, 0.219, 0.344, FG),       # 블로터 행 1
    (0.250, 0.656, 0.438, 0.563, DIM),      # 블로터 행 2
    (0.250, 0.781, 0.656, 0.781, ACCENT),   # 블로터 행 3 (강조)
)


def render(size: int) -> bytes:
    """RGBA 픽셀을 행 단위로 만든다."""
    rows = [[BG] * size for _ in range(size)]
    for x0, x1, y0, y1, color in SHAPES:
        # 작은 크기에서 도형이 통째로 사라지지 않게 최소 1px 을 보장한다.
        left, right = int(x0 * size), max(int(x1 * size), int(x0 * size) + 1)
        top, bottom = int(y0 * size), max(int(y1 * size), int(y0 * size) + 1)
        for y in range(top, min(bottom, size)):
            for x in range(left, min(right, size)):
                rows[y][x] = color
    return b"".join(
        b"\x00" + bytes(channel for pixel in row for channel in pixel) for row in rows
    )


def png(size: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)   # 8bit RGBA
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(render(size), 9))
        + chunk(b"IEND", b"")
    )


def ico(sizes: tuple[int, ...]) -> bytes:
    """PNG 를 그대로 담는 ICO. Windows Vista 이상이 읽는다."""
    images = [png(size) for size in sizes]
    offset = 6 + 16 * len(images)

    directory = b""
    for size, image in zip(sizes, images, strict=True):
        directory += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,   # 256 은 0 으로 적는다
            0 if size >= 256 else size,
            0, 0, 1, 32,
            len(image), offset,
        )
        offset += len(image)

    return struct.pack("<HHH", 0, 1, len(images)) + directory + b"".join(images)


def main() -> None:
    target = Path(__file__).resolve().parent / "ficc.ico"
    target.write_bytes(ico(SIZES))
    print(f"{target}  ({target.stat().st_size:,} bytes, {len(SIZES)} sizes)")


if __name__ == "__main__":
    main()
