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
relative to one segment (they then move with it). `fade` defaults to 0.12;
`fade_in` / `fade_out` set one side only (a fade to black is a full-frame
overlay with `fade_in` and `"fade_out": 0` at the end).
`aspects: ["9:16"]` limits an overlay to some sizes.

| Kind | Fields |
|---|---|
| Text | `text` (`\n` breaks a line, `*word*` highlights), `style`, `pos`, optional `size` (multiplier), `align`, `color`, `bg`, `y` (0 to 1), `icon` (image shown before the words) |
| Image | `image` (path), `width` (fraction of frame width), `pos` |
| Animation | `gfx` (name of a rendered HyperFrames project) or `video` (path to a file with alpha) |

Styles: `hook`, `caption`, `title`, `label`, `cta`, `hand`, `plain`, `display`.
Positions: `top`, `upper`, `center`, `lower`, `caption`, `bottom`. Both are
defined in `templates/overlay.css`, with safe zones per aspect.

## Per-ad styles

An `ad.css` next to `timeline.json` loads after the brand and overlay styles,
so one ad can use a partner's font or tweak a style without touching the
brand kit. Use absolute `file://` URLs for its `@font-face` sources.

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

## vo (voiceover lines)

```json
"vo": [{"text": "Right on Detroit Ave in Lakewood.", "at": 9.8, "gain_db": 0},
       {"file": "vo/my-take-02.wav", "at": 11.85}]
```

`adstudio voice <brand>/<ad>` makes a scratch take for every line that only has
`text` (Fish Audio S2.1 Pro on Runware, your Runware key) and saves word timings
for every line, so captions follow the voice. `at` is where the first word lands.
To use your own recording, set `file` (and drop `text`), then run `voice` again.
A line can also be a clip's own sound, `{"clip": "<id>", "in": 0.15, "out": 7.45,
"at": 2.5}`, so someone keeps talking while the picture cuts away (mute those
footage segments with `volume: 0`).
Settings: `adstudio config voice_id adrian` (adrian, ethan, jordan, laura, sarah,
hannah, selene, or any Fish voice id) and `voice_speed` (0.5 to 2). VO is speech,
so `music.duck` lowers the music under it; set `"duck": false` for a steady bed.
`captions: false` on a line leaves it uncaptioned. Captions spell words as the
line's `text` (or `caption`, when the screen should read differently from what is
said, like `"text": "open twenty four seven"`, `"caption": "Open 24/7"`).

## What the Premiere XML carries

Cuts on the original files, reframing as Scale and Position, overlays as
transparent PNGs on upper tracks, clip audio, music and SFX with levels.
Not carried: speed changes and overlay fades.
