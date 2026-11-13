# Posters set in Gran

Two layers: a model draws the background with **no text at all**, the template sets the letters in Gran. Image models
can't take a font file, so the text is never asked from them — it is real type laid out in HTML/canvas.

This folder holds the recipes, not the rendered artwork. Rendered posters are in [`../docs/`](../docs), and the
generated backgrounds (`gen/`) are not in the repo: they are heavy, and any generator can redo them from the prompts
below. Drop your own picture in as `gen/<style>.png` to render a poster.

The default words on the posters are Russian (`ГРАНЬ`); every line can be replaced through the query string.

## `styles/` — five moods from one template

Prompts for the backgrounds: [`styles/prompts.txt`](styles/prompts.txt).

| Style | Background | Type |
| --- | --- | --- |
| `faceted` | Dark navy crystal facets, cold cyan light | Black, white with glow |
| `concrete` | Brutalist concrete, one orange panel | Black, black type, orange rule |
| `concrete-behind` | Same frame, sky cut out and laid over the letters | Black type sits behind the building |
| `riso` | Risograph: fluorescent pink and cobalt on cream | Black, blue, multiply |
| `holo` | Crumpled holographic foil | Black, black type |
| `blueprint` | Cobalt technical drawing with a fine grid | Light, white |

```bash
# open the template in a browser with a style and your own words
open "styles/poster.html?style=concrete&title=ГРАНЬ&top=GRAN&b1=ЛАТИНИЦА+КИРИЛЛИЦА"
```

Canvas is 1088×1360 (4:5). The template is one file: the `S` object holds the per-style look (weight, fill colour,
blend mode, glow, grain), and the type is fitted to the width automatically. `concrete-behind` draws a PNG of the same
frame with a transparent sky on top of the letters, so the roof covers their bottom.

## `neon/` — dark HUD glow

[`neon/poster.html`](neon/poster.html), prompt in [`neon/prompts.txt`](neon/prompts.txt). Glowing ribbons are drawn by
the generator; the drip under the letters, the colour fringe and the grain are canvas.

Query string: `bg`, `title`, `top`, `topr`, `b1`, `b2`, `b3`, `seed` (drip shape).

## Render without a window

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --disable-gpu --hide-scrollbars --allow-file-access-from-files \
  --window-size=1088,1360 --virtual-time-budget=15000 \
  --screenshot=out.png "file://$PWD/poster.html?style=concrete-behind"
```

Chromium only loads the local `.woff2` files with `--allow-file-access-from-files`. Give the page a few seconds of
`--virtual-time-budget` so the background image and the fonts have time to arrive.

## Making a new style

1. Ask the generator for a background **without text**, and say plainly where the empty space for the headline should
   be ("the upper third is calm dark space, left clear for a headline"). Save the prompt next to the style.
2. Add a preset to `S` in `styles/poster.html`: weight, base line, fill colour, blend mode, grain.
3. Drop the picture in as `styles/gen/<name>.png` and render.

The type is Gran Black for the big word and Bold/Regular for the small lines. Gran is a display face: small lines work
from 20 px.
