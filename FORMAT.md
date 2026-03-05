# Huawei Notes PENCILENGINE `.bin` Format (Inferred, Partial)

This document describes the currently inferred structure for sample files:

- `53d1088bd634cba318c4d27cc9371070.bin`
- `9def0e3d381fa1c2e41f7f80d88503a3.bin`

All multi-byte numeric fields below are inferred as big-endian.

## 1) File Header

Offset | Size | Type | Meaning (inferred)
---|---:|---|---
`0x00` | 12 | ASCII | Magic: `PENCILENGINE`
`0x0C` | 4 | `u32` | Header length marker (`0x4C` in both samples)
`0x10` | 4 | `u32` | Version marker (`0x00010001`)
`0x58` | 4 | `u32` | Size-like field (`file_size - 124` in both samples)
`0x70` | 4 | `u32` | Stroke count (`139`, `141`)
`0x74` | 4 | `u32` | Payload-size-like (`file_size - 196`)
`0x80` | 4 | `u32` | Logical width-like value (`1000`)
`0x84` | 4 | `u32` | Unknown (`625`)

The first stroke chunk begins at `0x88` in both samples.

## 2) Stroke Chunk Container

Each stroke is stored sequentially. Let `S` be stroke start offset.

Offset (rel to `S`) | Size | Type | Meaning (inferred)
---|---:|---|---
`+0x00` | 4 | `u32` | Prelude marker `0x30`
`+0x04` | 4 | `u32` | Prelude flags (usually `0`)
`+0x08` | 4 | `u32` | Prelude version marker `0x00010001`
`+0x0C` | 4 | `u32` | Stroke id
`+0x10` | 16 | bytes | Stroke UUID-like bytes
`+0x20` | 4 | `u32` | Section marker `0x44`
`+0x24` | 4 | `u32` | Section marker `0x30`
`+0x28` | 4 | `u32` | Section marker `0x74`
`+0x2C..+0xA7` | 124 | mixed | Unknown metadata words/floats
`+0xA8` | 4 | `u32` | Point count
`+0xAC` | 4 | `u32` | Point stride (`0x24` = 36 bytes)
`+0xB0` | 8 | `u32,u32` | Reserved (`0,0` in samples)
`+0xB8` | `count*0x24` | bytes | Point records

Next stroke offset:

`S_next = S + 0xB8 + point_count * 0x24`

Both sample files end with a 72-byte trailing blob after the final stroke.

## 3) Point Record Encoding

Each point record is 36 bytes (`0x24`) and parses as:

`>ffIffffIf`

Field | Type | Meaning (inferred)
---|---|---
`x` | `f32` | X coordinate
`y` | `f32` | Y coordinate
`t_u32` | `u32` | Monotonic per-stroke time/order counter
`f3` | `f32` | Pressure-like value (`~0.004..0.87`)
`f4` | `f32` | Constant in samples (`2.3`)
`f5` | `f32` | Constant in samples (`10.0`)
`f6` | `f32` | Constant in samples (`0.2`)
`u7` | `u32` | State-like code (`4` or `6`)
`f8` | `f32` | Sequence/progression-like (`0..~104`)

## 4) Stroke Separation

Strokes are separated by chunk boundaries, not explicit pen-up markers in point records:

- parser reads `point_count` and `point_stride` from `+0xA8/+0xAC`.
- record list length determines exact stroke extent.
- next stroke starts immediately after last point record.

## 5) Coordinate Transform to Preview PNG

Using automatic registration against Huawei preview PNGs (`902x1080`), best transform for both sample pages:

- `scale ≈ 0.902`
- `dx ≈ -0.5`
- `dy ≈ -0.5`

This produced strong alignment:

- page 6: point-match `0.9138`, render precision `0.8307`
- page 8: point-match `0.9081`, render precision `0.7397`

So extracted coordinates are internally consistent and map to previews with a stable affine (scale+translate) transform.
