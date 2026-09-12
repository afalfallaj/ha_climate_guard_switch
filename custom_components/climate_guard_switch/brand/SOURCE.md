# Brand icon source

These images are generated, not hand-designed artwork:

- **Glyph**: `mdi:water-thermometer` from [Material Design Icons](https://pictogrammers.com/library/mdi/icon/water-thermometer/) (Pictogrammers), licensed [Apache License 2.0](https://github.com/Pictogrammers/MaterialDesign/blob/master/LICENSE).
- **Why this glyph**: this integration's primary example use case is guarding a water heater/cooler by run time and cooldown — a droplet + thermometer reads as "temperature-guarded water device" at a glance.
- **Generation**: SVG fetched from the Iconify API (`https://api.iconify.design/mdi/water-thermometer.svg`), recolored (`#3B4252` for the light-theme files, `#FFFFFF` for the `dark_*` files) via a plain text substitution of `currentColor`, then rasterized with `cairosvg` to the file/dimension set Home Assistant's brand-images mechanism expects: `icon.png`/`dark_icon.png` at 256×256, `logo.png`/`dark_logo.png` at 512×512, and `@2x` variants at double each.

Swap these files (same names/dimensions) for bespoke artwork whenever real branding exists — no code or manifest change needed, see `AGENTS.md`.
