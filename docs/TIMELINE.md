# timeline.json

One file per ad at `ads/<brand>/<ad>/timeline.json` in your workspace. Times are seconds.

```json
{
  "version": 1,
  "brand": "my-brand",
  "name": "my-ad",
  "fps": 30,
  "aspects": ["9:16", "4:5", "1:1"],
  "segments": [],
  "overlays": [],
  "captions": {"max_words": 3},
  "music": null,
  "sfx": []
}
```

Aspects: `9:16`, `4:5`, `1:1`, `16:9`. The first is the default for `preview` and `xml`.

## segments (played in order)

| Kind | Fields |
|---|---|
| Footage | `clip` (id or unique fragment), `in`, `out`, optional `speed` (0.25 to 4), `volume` (0 mutes, default 1), `captions: false` |
| Still | `image` (path) or `clip` of an ingested image, `dur` |
| Colour card | `color` (`#rrggbb` or a name from brand.css such as `paper`, `ink`, `deep`), `dur` |

Framing, any kind: `focus: [x, y]` (0 to 1, the point kept in frame when cropping;
shot logs give `subject_x`, `subject_y`), `focus_by_aspect: {"1:1": [x, y]}`,
`zoom` (1 or more), `fit: "contain"` (whole frame over a blurred fill, instead of cropping).

## overlays

Each has `start` and `end` on the ad's clock, or `seg: <index>` to make them
relative to one segment (they then move with it). `fade` defaults to 0.12.
`aspects: ["9:16"]` limits an overlay to some sizes.

| Kind | Fields |
|---|---|
| Text | `text` (`\n` breaks a line, `*word*` highlights), `style`, `pos`, optional `size` (multiplier), `align`, `color`, `bg`, `y` (0 to 1) |
| Image | `image` (path), `width` (fraction of frame width), `pos` |
| Animation | `gfx` (name of a rendered HyperFrames project) or `video` (path to a file with alpha) |

Styles: `hook`, `caption`, `title`, `label`, `cta`, `hand`, `plain`, `display`.
Positions: `top`, `upper`, `center`, `lower`, `caption`, `bottom`. Both are
defined in `templates/overlay.css`, with safe zones per aspect.

## captions

`null` for none. Otherwise built from the Parakeet transcript of every footage
segment that has sound: `max_words` (3), `max_chars` (18), `upper`, `style`, `pos`, `size`.

## music and sfx

```json
"music": {"file": "library/music/x.mp3", "gain_db": -16, "duck": true,
          "start": 0, "at": 0, "fade_out": 0.8, "loop": false},
"sfx": [{"file": "library/sfx/whoosh.mp3", "at": 3.4, "gain_db": -6}]
```

`start` is where to begin inside the music file, `at` is where it enters the ad.
`duck` lowers music under speech. Finals are normalised to -14 LUFS.

## What the Premiere XML carries

Cuts on the original files, reframing as Scale and Position, overlays as
transparent PNGs on upper tracks, clip audio, music and SFX with levels.
Not carried: speed changes and overlay fades.
