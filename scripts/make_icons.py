
"""Generate the PWA icon PNGs without any imaging dependencies.

Draws the Jarvis orb motif (cyan ring on the app's dark background)
at 4x resolution, box-downsamples for antialiasing, and writes
minimal RGBA PNGs using only zlib/struct from the standard library.
"""

import struct
import zlib
from pathlib import Path

FRONTEND_PUBLIC = (
    Path(__file__).resolve().parents[1]
    / "frontend" / "web" / "public" / "icons"
)

BACKGROUND = (8, 11, 18, 255)        # #080b12
RING = (125, 220, 255, 255)          # #7ddcff
RING_DIM = (125, 220, 255, 110)
CORE = (158, 236, 255, 255)


def render_icon(size, ring_radius_ratio, thickness_ratio):
    scale = 4
    big = size * scale
    center = big / 2
    radius = big * ring_radius_ratio
    thickness = big * thickness_ratio

    samples = bytearray(big * big * 4)

    glow = thickness * 1.35
    core_radius = thickness * 0.8

    for y in range(big):
        dy = y + 0.5 - center

        for x in range(big):
            dx = x + 0.5 - center
            distance = (dx * dx + dy * dy) ** 0.5
            offset = distance - radius
            absolute = abs(offset)

            index = (y * big + x) * 4

            if distance <= core_radius:
                color = CORE
            elif absolute <= thickness * 0.5:
                color = RING
            elif absolute <= glow:
                fade = 1.0 - (absolute - thickness * 0.5) / (glow - thickness * 0.5)
                color = (
                    RING_DIM[0],
                    RING_DIM[1],
                    RING_DIM[2],
                    int(RING_DIM[3] * fade),
                )
            else:
                color = BACKGROUND

            samples[index] = color[0]
            samples[index + 1] = color[1]
            samples[index + 2] = color[2]
            samples[index + 3] = color[3]

    out = bytearray(size * size * 4)

    for y in range(size):
        for x in range(size):
            red = green = blue = alpha = 0

            for sy in range(scale):
                for sx in range(scale):
                    index = (
                        (y * scale + sy) * big
                        + x * scale
                        + sx
                    ) * 4

                    alpha_p = samples[index + 3]

                    red += samples[index] * alpha_p
                    green += samples[index + 1] * alpha_p
                    blue += samples[index + 2] * alpha_p
                    alpha += alpha_p

            out_index = (y * size + x) * 4

            if alpha == 0:
                out[out_index:out_index + 4] = bytes(BACKGROUND)
            else:
                out[out_index] = red // alpha
                out[out_index + 1] = green // alpha
                out[out_index + 2] = blue // alpha
                out[out_index + 3] = 255

    return bytes(out)


def write_png(path, size, pixels):
    def chunk(tag, data):
        payload = tag + data

        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    raw = b"".join(
        b"\x00" + pixels[row * size * 4:(row + 1) * size * 4]
        for row in range(size)
    )

    header = struct.pack(
        ">IIBBBBB",
        size,
        size,
        8,
        6,
        0,
        0,
        0,
    )

    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )

    print(f"wrote {path} ({size}x{size})")


def main():
    # Full-bleed icons for the manifest "any" purpose.
    write_png(
        FRONTEND_PUBLIC / "icon-512.png",
        512,
        render_icon(512, ring_radius_ratio=0.33, thickness_ratio=0.045),
    )
    write_png(
        FRONTEND_PUBLIC / "icon-192.png",
        192,
        render_icon(192, ring_radius_ratio=0.33, thickness_ratio=0.045),
    )

    # Maskable variant keeps the motif inside the inner 80% safe zone.
    write_png(
        FRONTEND_PUBLIC / "icon-512-maskable.png",
        512,
        render_icon(512, ring_radius_ratio=0.24, thickness_ratio=0.034),
    )


if __name__ == "__main__":
    main()
