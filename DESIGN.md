---
name: Compass
description: A one-bit desktop — two inks, ordered dithers instead of grays, and every surface a window.
colors:
  ink: "#000000"
  paper: "#ffffff"
typography:
  display:
    fontFamily: "Silkscreen, 'Courier New', monospace"
    fontSize: "clamp(40px, 9vw, 64px)"
    fontWeight: 400
    lineHeight: 1
    fontFeature: "tabular-nums"
  headline:
    fontFamily: "Silkscreen, 'Courier New', monospace"
    fontSize: "clamp(20px, 4vw, 30px)"
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: "0"
  title:
    fontFamily: "Silkscreen, 'Courier New', monospace"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.2
  chrome:
    fontFamily: "Silkscreen, 'Courier New', monospace"
    fontSize: "10px"
    fontWeight: 400
    lineHeight: 1
  readout:
    fontFamily: "Silkscreen, 'Courier New', monospace"
    fontSize: "38px"
    fontWeight: 400
    lineHeight: 1.1
    fontFeature: "tabular-nums"
  numeral:
    fontFamily: "Silkscreen, 'Courier New', monospace"
    fontSize: "17px"
    fontWeight: 400
    fontFeature: "tabular-nums"
  body:
    fontFamily: "Geneva, Verdana, 'DejaVu Sans', sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.55
  body-small:
    fontFamily: "Geneva, Verdana, 'DejaVu Sans', sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.55
  caption:
    fontFamily: "Geneva, Verdana, 'DejaVu Sans', sans-serif"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "Silkscreen, 'Courier New', monospace"
    fontSize: "9px"
    fontWeight: 400
    lineHeight: 1.35
  micro:
    fontFamily: "Silkscreen, 'Courier New', monospace"
    fontSize: "8px"
    fontWeight: 400
rounded:
  none: "0"
  disc: "50%"
spacing:
  hair: "1px"
  xs: "4px"
  sm: "8px"
  md: "12px"
  gap: "16px"
  shell: "32px"
components:
  window:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
  window-title:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    typography: "{typography.chrome}"
    padding: "5px 6px 4px 8px"
    height: "20px"
  window-body:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    padding: "12px 14px"
  window-status:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    padding: "4px 8px 3px"
  window-grip:
    size: "13px"
  button:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.chrome}"
    rounded: "{rounded.none}"
    padding: "7px 12px 6px"
  button-active:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  button-primary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.chrome}"
    rounded: "{rounded.none}"
    padding: "7px 12px 6px"
  button-compact:
    typography: "{typography.label}"
    padding: "4px 8px 3px"
  input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "5px 7px"
    width: "100%"
  field-label:
    textColor: "{colors.ink}"
    typography: "{typography.label}"
  checkbox:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.none}"
    size: "13px"
  radio:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.disc}"
    size: "13px"
  badge:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.micro}"
    rounded: "{rounded.none}"
    padding: "3px 5px 2px"
  badge-warn:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  menubar:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.chrome}"
    height: "25px"
    padding: "0 10px"
  menu-item:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.chrome}"
    padding: "4px 8px 3px"
  menu-item-hover:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  desk-icon:
    typography: "{typography.label}"
    width: "92px"
    padding: "5px 2px 4px"
  desk-icon-active:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  desk-status:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    padding: "5px 10px 4px"
  stat-tile:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    padding: "8px 6px"
  stat-value:
    typography: "{typography.numeral}"
  stat-label:
    typography: "{typography.micro}"
  meter-track:
    backgroundColor: "{colors.paper}"
    height: "11px"
    padding: "1px"
  meter-cell-on:
    backgroundColor: "{colors.ink}"
  log-row:
    typography: "{typography.body}"
    padding: "6px 8px"
  state-box:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    size: "14px"
  state-box-verified:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  toast:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: "8px 10px"
---

# Design System: Compass

## Overview

**Creative North Star: "The Printed Desktop"**

Compass is drawn the way a one-bit workstation was drawn: one ink on one paper, with every intermediate value achieved by knocking pixels out of a tile rather than by mixing. The two tokens are literally named `--ink` and `--paper`, and that naming is the whole thesis — this is not a palette that happens to be monochrome, it is a printing process with a single plate. Grays do not exist; ordered dithers stand in for all of them. The desktop ground itself is a 25% dither, so every window sits on visible tooth rather than on flat white.

The lineage is the early one-bit desktop operating system: a sticky menu bar with a working pull-down, an icon column where destinations are objects you select, one-pixel window chrome with an inverted title bar, a segmented status bar along a window's foot, a hatched resize grip in its trailing corner, and marching ants around a selection. Density is tight and instrumented — 13px body text, 8-to-10px chrome type, 1px rules, 16px between windows — because the system's job is to show counted, stamped, verified quantities rather than to breathe. Nothing eases: there is not one `transition` declaration in the stylesheet, so state changes snap, and the animations that do exist run on `steps()`.

The confirmed anti-reference is the cream-and-sage rounded-card rendition this world replaced: a `#f6f3ec` ground, a `#4c8a3f` sage accent, Segoe UI over Georgia, soft radii and an even grid of equal cards. That was the AI-default look, and escaping it is the reason this world exists. Any drift back toward a warm neutral background, a single tasteful accent hue, a system-UI/serif pairing, or a page built as a lawn of identical rounded panels is a regression, not a variation.

**Key Characteristics:**
- Two inks and no third colour anywhere in the system.
- Ordered dither tiles instead of grays, used for fills, grounds, bars and shadows.
- Classification carried by pattern, never by hue.
- One-pixel chrome; zero corner radius on every rectangle.
- Silkscreen as the chrome voice, Geneva as the body voice.
- Authored 12-grid pixel icons; no emoji, no icon font.
- Stepped motion, instant state changes, dithered drop shadows.

## Colors

The palette is exactly two values, and everything between them is a pattern rather than a colour.

### Primary
- **Absolute Ink** (`#000000`): every stroke, every rule, every glyph, every filled state. It is the border on all chrome, the ground of an inverted title bar, the fill of a lit meter cell, and the text colour of all running prose. There is no lighter variant — an "80% ink" is expressed by a dither tile, not by a second value.

### Neutral
- **Bare Paper** (`#ffffff`): the ground of every window, control, input, badge and tile, and the knockout colour for text and glyphs inside inverted chrome. The page body is paper *plus* the 25% dither, so paper at full strength always reads as a surface lifted off the desktop.

### The Pattern Scale

Where another system keeps a gray ramp, this one keeps an ordered tile set. These are real tokens on `:root` (`--d12` … `--knock50`) rendered as 2px and 4px SVG data URIs with `shape-rendering: crispEdges`, and always painted with `background-size` matched to the tile so the pattern stays pixel-exact. They are the tonal ladder:

- **12% Speckle** (`--d12`, 4px tile): the lightest tint. Row striping in tables, list-item and player-card hover, hero and podium grounds, the soft-glow habitat, the `unclear` attention class.
- **25% Ground** (`--d25`, 2px tile): the desktop itself, the scrollbar track, podium bars, and the default button hover.
- **50% Half** (`--d50`, 2px tile): the workhorse. Every drop shadow, every bar-chart column, the half-lit meter cell, the `supporting_work` attention class, the in-focus presence dot, the companion's cast shadow.
- **75% Dense** (`--d75`) and **87% Near-Solid** (`--d87`): the dark end of the ladder, held in reserve for fills that must read as almost-ink without being ink.
- **Forward Hatch** (`--hatch`, 4px diagonal): the window resize grip, the boss HP fill, the danger button, the ember habitat and ember avatar.
- **Back Hatch** (`--hatch-back`, 4px counter-diagonal): reserved for opposition — the `off_task` attention class and the destructive button.
- **Vertical Stripe** (`--vstripe`) and **Horizontal Stripe** (`--hstripe`): the `unmonitored` attention class, the bubbles habitat, and tidepool avatars.
- **4px Checker** (`--checker4`): the coarsest tile, available as a coat and fill pattern.
- **Knockout Half** (`--knock50`, 2px tile of paper pixels): the only *subtractive* tile. It is laid over a control as a pseudo-element to dim it, removing half its pixels instead of reducing opacity.

### Named Rules

**The Two-Ink Rule.** There are exactly two colour values in this system: `#000000` and `#ffffff`. No third colour token exists, and none may be introduced — not for a brand accent, not for success or danger, not for a chart series. If a design needs another value, it needs another pattern.

**The Pattern-Not-Colour Rule.** Categorical meaning is carried by dither pattern and always accompanied by a labelled key. The five-class focus attention timeline is the reference implementation: `direct_work` is solid ink, `supporting_work` is 50% dither, `off_task` is back-hatch, `unclear` is 12% dither, `unmonitored` is vertical stripe — each swatch repeated at 11px in a legend beneath the bar. Any new classification follows the same shape: distinct tile, visible legend.

**The Solid Ground Rule.** Text sits only on solid black or solid white — never on a dither. Dithers are for fills, grounds, bars and shadows. Where prose has to appear over a dithered surface it gets plated first: the hero paragraph, the desk-icon label and the leaderboard note all carry their own paper background, and inverting to ink-on-paper is always preferred to dithering behind type.

## Typography

**Display Font:** Silkscreen (self-hosted at `/fonts/silkscreen-400.woff2` and `-700.woff2`, both preloaded; falls back to Courier New, monospace)
**Body Font:** Geneva (falling back to Verdana, DejaVu Sans, sans-serif)
**Label/Mono Font:** Silkscreen — the same face as display; this system has one chrome voice at many sizes.

**Character:** Silkscreen is a bitmap face with no optical smoothing, and the whole document turns font smoothing off (`-webkit-font-smoothing: none`) so it renders as drawn pixels rather than as anti-aliased type. It carries all machinery: title bars, buttons, menus, labels, status fields, numerals. Geneva carries all human sentences. The pairing is deliberately unequal — the chrome is loud, small and uppercase; the prose is quiet, plain and lowercase.

Recorded honestly as an open issue rather than a decision: **the body voice is unowned off macOS.** Geneva ships only on Apple systems; elsewhere the stack falls to Verdana, a materially wider face, so line lengths and window rhythm shift for most visitors. Nothing in the build pins this down. Treat a self-hosted body face as unfinished work, not as settled.

### Hierarchy
- **Display** (Silkscreen 400, `clamp(40px, 9vw, 64px)`, line-height 1, tabular numerals): the focus session timer, and nothing else. This is the largest type in the system by a wide margin.
- **Headline** (Silkscreen 400, 20px, line-height 1.2, letter-spacing 0): the `h1` element. Note that on window-structured screens the `h1` is visually hidden (see the Window Names Nothing Rule) — headline type is visible mainly on hero surfaces, which scale it `clamp(20px, 4vw, 30px)`.
- **Title** (Silkscreen 400, 14px, line-height 1.2): the `h2` element in document flow, e.g. a social section heading at 13px.
- **Chrome** (Silkscreen 400, 10px, line-height 1): window title bars, buttons, menu-bar items and pull-down entries, hero links, timer state. Uppercase everywhere it labels a control; sentence case in a window title, which is a name rather than a command.
- **Readout** (Silkscreen 400, 38px, line-height 1.1, tabular numerals): the focus alignment score — the one number the attention view exists to deliver. Below Display and above every other numeral.
- **Numeral** (Silkscreen 400, 17px, tabular numerals): stat tile values and the recovery code. The same tabular treatment appears at 13px in rank cells and 12px in scores.
- **Body** (Geneva 400, 13px, line-height 1.55, max-width 68ch): all running prose. Hero paragraphs cap at 58ch and the leaderboard note at 60ch.
- **Body Small** (Geneva 400, 12px): the systematic secondary step — `.muted`, table cells, list-item text, monitoring disclosures. The most-used size in the system after body.
- **Caption** (Geneva 400, 11px): the tertiary step — `.small`, `h3`, inline `code`, the leaderboard note. Below this, type switches to Silkscreen and uppercase.
- **Label** (Silkscreen 400, 9px, uppercase): form labels, window and desktop status fields, meter heads, table headers, legend keys, desk-icon labels (sentence case here, since they are object names).
- **Micro** (Silkscreen 400, 8px, uppercase): badges, stat-tile labels, presence indicators, log-row source lines, bar-chart labels. This is the floor; nothing goes below 8px, and no size sits between the documented steps.

### Named Rules

**The Two Voices Rule.** Silkscreen is chrome and Geneva is content, and they never trade jobs. A sentence a person reads is never set in Silkscreen; a control, label, status field or counted number is never set in Geneva. When in doubt, ask whether the string is part of the machine or part of the message.

**The Tabular Readout Rule.** Any number that changes in place — timers, XP, scores, ranks, meter values — is set with `font-variant-numeric: tabular-nums` so digits do not shift the layout as they tick.

## Layout

The shell is a three-row CSS grid: a 25px sticky menu bar spanning full width, a body row, and an auto-height desktop status bar spanning full width. Below the menu bar the body splits into a fixed **104px icon column** and a fluid main panel. The icon column is itself sticky at `top: 25px`, so navigation stays parked under the menu bar while content scrolls past it. The main panel is capped at 1180px with 16px side padding and 40px of foot clearance.

Inside the panel, content is composed of stacked windows separated by the single spacing token `--gap: 16px`. Two recurring grids do the arranging: a two-column window layout (`repeat(auto-fit, minmax(300px, 1fr))`, 16px gap, top-aligned) and a tile strip (`repeat(auto-fit, minmax(112px, 1fr))`) with **zero gap** and a shared 1px frame, so stat tiles read as one instrument rather than as separate cards. The spacing rhythm is short and mostly even: 1px hairlines, 4px, 8px, 12px, 16px, with 32px reserved for the centred 620px onboarding shell.

Three breakpoints, all max-width:
- **900px** — the three-up player grid drops to two columns.
- **760px** — the desktop breaks down: the icon column is hidden and replaced by a fixed bottom dock, the shell collapses to one content column with 12px padding, the status bar gains 56px of bottom margin to clear the dock, and the menu bar drops the user's name.
- **600px** — the phone pass: player grid to one column, hero and co-op launcher stack, podium tightens and its blurbs are hidden, leaderboard rows drop the trend column, window body padding tightens to 10px/11px.

### Named Rules

**The Whole-Pixel Rule.** Every measurement in this system is a whole pixel and every drawn thing is snapped to its grid. Pixel icons render at integer multiples of 12 (12, 24, 36, 48); the companion frame snaps to a whole multiple of 24 before drawing; dither backgrounds set `background-size` to their exact tile size; `image-rendering: pixelated` and `shape-rendering: crispEdges` are applied at the raster. Fractional sizes produce interpolated pixels, which is the one thing this world cannot survive.

**The Plated Content Rule.** Running text never sits directly on the dithered desktop. Content lives inside a window, or on an element that carries its own paper background and 1px frame.

## Elevation & Depth

There is no blur in this system and no soft shadow anywhere. Depth is built from two moves: a 1px ink frame that separates a surface from its ground, and a **dithered offset block** behind it. Every window, card, toast, player card, hero and leaderboard sheet carries a `::before` pseudo-element inset `top: 3px; left: 3px; right: -3px; bottom: -3px` and filled with the 50% dither at `z-index: -1`, so a 3px band of half-tone ink emerges from the lower-right edges. That half-tone band is the material — it reads as a printed shadow because it is literally a halftone, and it is what makes the desktop ground feel like it sits *behind* the window rather than beside it.

This is worth stating plainly for anyone auditing the system: **the offset shadow here is not the neobrutalist solid-block shadow.** A hard `4px 4px 0 #000` slab is a decorative refusal of depth; this is a dithered plate at 50% density, drawn from the same tile set as every other tonal value in the world, in a world whose entire depth vocabulary is halftone. The world earns it. A solid offset block is not a permitted substitute.

Two real `box-shadow` declarations exist, and both are structural rather than atmospheric — they draw extra strokes, not light.

### Shadow Vocabulary
- **Dithered plate** (`::before` at `top:3px; left:3px; right:-3px; bottom:-3px`, `background-image: var(--d50)`, `background-size: 2px 2px`, `z-index: -1`): the standard lift for any floating surface — windows, cards, toasts, player cards, heroes, the leaderboard sheet.
- **Double frame** (`box-shadow: 0 0 0 1px var(--paper), 0 0 0 2px var(--ink)`, with `margin: 2px` to reserve the ring): the default-button ring on `.primary`. It marks the button the Return key would press, exactly as the source lineage did.
- **Menu drop** (`box-shadow: 3px 3px 0 -1px var(--paper), 4px 4px 0 -1px var(--ink)`): the pull-down menu's edge — a paper gap then a 1px ink line, so the menu reads as a sheet lifted a hair above the bar rather than as a shaded slab.

### Named Rules

**The Halftone Shadow Rule.** Depth is a 3px dithered plate offset down and right, never a blur, never an opacity ramp, and never a solid offset block. If a surface needs to lift, it takes the plate; if it does not, it takes a 1px frame and nothing else.

**The One-Pixel Chrome Rule.** Structural borders are `1px solid var(--ink)`. 2px is the only escalation and it means urgency or rank: an error note, a live monitor that is actively sharing, a first-place podium card. Dotted 1px is the de-escalation, used for divisions inside a surface — list rows, log rows, leaderboard rows, rules, and advisory boxes.

## Shapes

Every rectangle in this system is a rectangle. `border-radius: 0` is set explicitly on buttons, inputs, selects, textareas and menu titles, and no other element introduces a radius — with exactly one exception, the radio input and its selected dot, which are circles because a radio button is a disc by nature and a square radio would read as a checkbox. That is the entire curve budget.

The recurring silhouette is the window: a 1px ink rectangle, an inverted title bar 20px tall along the top, a paper body, an optional segmented status bar along the foot whose fields are divided by 1px verticals and whose last field is pushed right with 18px of extra padding, and a 13px hatched grip anchored in the bottom-right corner with a 1px border on its top and left edges. Anything that needs to hold content takes that silhouette.

Small geometry is drawn on grids rather than described with CSS: icons on a 12×12 grid, the companion on a 24×24 grid, both rendered as merged horizontal runs so a glyph ships as a few dozen `rect` elements instead of hundreds. Checkbox ticks are a `clip-path` polygon, and the select chevron is a hand-drawn 9×6 stepped triangle rather than a font glyph or a smooth SVG path.

### Named Rules

**The Zero Radius Rule.** Corner radius is `0` on every surface, control, badge, tile and container. The sole exception is `input[type='radio']` and its dot at `50%`. Pills, rounded cards and softened buttons are out of the world.

**The Twelve Grid Rule.** Any new icon is authored as a 12×12 string grid of `#` and `.` in `PixelIcon.tsx`, alongside the existing 50 glyphs — not imported from an icon library, not traced from an SVG, not set as a font glyph.

## Components

The overall feel is *instrumented and mechanical*: one-pixel frames, uppercase chrome, counted readouts, instant state changes. Controls look like they were stamped rather than styled.

### Buttons
- **Shape:** Square (`border-radius: 0`), 1px ink frame, paper ground, Silkscreen at 10px, uppercase, with a 6px gap so a pixel icon can sit inside the label.
- **Default:** paper ground, ink text, `7px 12px 6px` padding (the asymmetric vertical is bitmap-type optical centring — keep it).
- **Hover:** the ground takes the 25% dither. **Active:** full inversion — ink ground, paper text, dither cleared. There is no transition; the change is instant.
- **Primary:** the same button wearing the double frame (`0 0 0 1px paper, 0 0 0 2px ink`) with `margin: 2px` reserving room for the ring. It is the default action, not a coloured emphasis — there is no colour to emphasise with.
- **Danger:** back-hatch fill at rest, inverting to solid ink on hover. Opposition is a pattern, consistent with the attention timeline's `off_task` class.
- **Disabled:** `cursor: not-allowed` plus a `::after` overlay of the knockout tile, which removes half the button's pixels. The system dims by subtraction, never by opacity.
- **Compact:** buttons inside a window title bar or card header step down to 9px and `4px 8px 3px`.

### Cards / Containers
- **Corner Style:** square, zero radius.
- **Background:** paper, on a 25% dithered desktop.
- **Shadow Strategy:** the dithered plate (see Elevation & Depth).
- **Border:** 1px solid ink, escalating to 2px only for urgency or rank.
- **Internal Padding:** `12px 14px` in a window body, tightening to `10px 11px` under 600px. Windows are separated by the 16px gap token.
- The `Card` component is the window: optional title bar, body, optional segmented status bar of left-to-right fields with the last pushed right, and the hatched grip which appears only when a status bar does.

### Inputs / Fields
- **Style:** 1px ink frame, paper ground, zero radius, `5px 7px` padding, full width, body font at 13px, with a block-shaped caret (`caret-shape: block`) so the insertion point matches the bitmap world.
- **Label:** a block-level Silkscreen 9px uppercase line, `12px 0 4px`, sitting above the field.
- **Placeholder:** ink at full opacity, italic — legibility is preserved and the distinction is carried by slant rather than by a lighter gray, which does not exist.
- **Focus:** a 2px dashed ink outline offset 2px. Inside inverted chrome (title bars, menu bar, active desk icons, an active button, your own leaderboard row) the ring flips to paper, or it would draw black on black.
- **Select:** native appearance stripped, 24px right padding, and a hand-drawn 9×6 stepped triangle as the chevron.
- **Checkbox / Radio:** 13px squares (the checkbox tick is a clip-path polygon; the radio is a disc with a 7px dot). Range inputs get a 5px framed track and a 9×13 framed thumb.

### Navigation
Navigation exists in three coordinated forms.
- **Menu bar:** 25px tall, sticky, paper with a 1px bottom rule, Silkscreen 10px. It holds the brand (a compass glyph plus the wordmark, Silkscreen 700), a working **Go** pull-down, and the signed-in user pushed right. The pull-down inverts its title while open, and its list is a 168px-minimum paper sheet with the menu-drop shadow, ink-inverting rows, a 1px separator at 35% opacity, and a `·` marking the current page.
- **Desktop icon column:** 104px wide, sticky, one 92px icon cell per destination — a 36px pixel icon over a Silkscreen 9px label on a paper plate. Hover inverts only the label; the active state inverts both glyph and label. Destinations are objects you select, so selection is inversion, not underline or accent.
- **Mobile dock:** below 760px the column becomes a fixed bottom bar of the first five destinations at 24px icons with 8px labels, keeping the same inversion for the active item and the same 1px top rule. The remaining destinations stay reachable through the Go menu — which is why the menu exists.
- **Desktop status bar:** full width along the foot, 1px top rule, Silkscreen 9px fields divided by 1px verticals with the last pushed right.

### Meter
A level you can count. Twenty cells inside an 11px framed track with 1px gaps and 1px inner padding: filled cells are solid ink, and a single trailing cell takes the 50% dither when the remainder is at least 0.34 of a cell. A smooth bar would be unreadable here — with no fill colour there is no percentage to judge — but squares can always be counted. The head is a Silkscreen 9px uppercase label with a tabular value pushed right.

### Pixel Icon System
Fifty glyphs authored as 12×12 string grids, rendered as merged horizontal runs in `currentColor` so a glyph inverts automatically inside inverted chrome. Twenty-two semantic aliases map product concepts to glyphs (`streak` → fire, `privacy` → lock, `evidence` → file), and `iconFor()` translates the seventeen emoji the API still emits into drawn glyphs at the design layer, so the server can keep storing emoji while the interface never renders one.

### Companion
The product's face, drawn as one-bit pixel art on a 24×24 grid. The silhouette is authored as a mask and the 1px outline is *computed* from that mask at render time, so it can never drift from the shape. The body is paper-white inside the hard outline and pattern is confined to the coat from row 16 down, so the face never competes with texture. Because there is no colour, the character's palette enum selects a **coat pattern** and its aura enum becomes the **habitat's own material** — a framed square behind the creature that takes a dither, a dotted border, or a stripe. The creature casts a 10×1 dithered shadow, not a soft one.

### Evidence Log
The system's signature readout: a framed list of rows on a `20px 1fr auto` grid, dotted 1px dividers, a 14px `StateBox` at the left (a one-bit checkbox that reports a fact rather than accepting input — inverted to ink with a paper tick when verified), the event in body type with a Silkscreen 8px uppercase source line, and a tabular Silkscreen 9px timestamp pushed right. A newly verified row animates in with `print`: a `clip-path` inset opening top-to-bottom over 0.4s in 5 steps, so the entry lays down a band at a time the way a line printer would, clipped so it never covers its neighbour.

### Named Rules

**The Window Names Nothing Rule.** A window title bar is chrome, never the document heading. Screens structured as windows name themselves with `PageTitle`, a visually hidden `h1`, so every page has exactly one `h1` and exactly one visible page-title treatment. Never promote a window title to the page heading, and never add a second visible page banner above the windows.

**The Drawn Glyph Rule.** No emoji renders anywhere in the interface. Every symbol is an authored 12-grid glyph; server-supplied emoji are translated by `iconFor()` at the design layer rather than by changing what the server stores.

**The Knockout Rule.** A disabled or dimmed control is dimmed by knocking pixels out of it with the `--knock50` tile laid over it as a pseudo-element. Never `opacity`, never a lighter ink — neither exists in a one-bit world.

## Do's and Don'ts

### Do:
- **Do** build every panel as a window: 1px ink frame, inverted title bar (min-height 20px, `5px 6px 4px 8px`), paper body (`12px 14px`), optional segmented status bar, hatched 13px grip in the trailing corner.
- **Do** express every intermediate value as an ordered dither tile from the existing set (`--d12`, `--d25`, `--d50`, `--d75`, `--d87`, `--hatch`, `--hatch-back`, `--vstripe`, `--hstripe`, `--checker4`), painted with `background-size` matched to the tile.
- **Do** carry classification with pattern plus a labelled legend, following the five-class attention timeline: solid ink, 50% dither, back-hatch, 12% dither, vertical stripe.
- **Do** keep text on solid black or solid white; plate it with its own paper background if it must sit over a dithered surface.
- **Do** mark selection and active state by inversion — ink ground, paper text — and mark an in-progress selection with the travelling marching-ants border (`0.5s linear infinite`, 3px dashes on a scrolling gradient).
- **Do** dim disabled controls with the `--knock50` overlay.
- **Do** set every number that ticks in `font-variant-numeric: tabular-nums`.
- **Do** author new icons as 12×12 string grids in `PixelIcon.tsx` and render them at integer multiples of 12.
- **Do** step motion (`steps(n, jump-none)`) and honour both `prefers-reduced-motion: reduce` and `:root[data-motion='off']`, which switch every animation off.

### Don't:
- **Don't** introduce a third colour. There are two values, `#000000` and `#ffffff`, and no colour token exists to extend.
- **Don't** encode meaning in hue, tint or saturation — there is none to encode with. Pattern carries classification.
- **Don't** set type over a dither, and don't use a dither as a "light gray text" substitute.
- **Don't** add a corner radius. Everything is square except `input[type='radio']`.
- **Don't** use blur, opacity ramps, gradients (other than the marching-ants dash pattern), or a solid offset block for depth. Depth is the 3px 50%-dither plate.
- **Don't** ease anything. There is not one `transition` in the stylesheet; state changes are instant and animations run on `steps()` — the single exception is marching ants at `linear`, where the 3px dash pattern is itself the quantisation.
- **Don't** render an emoji, an icon font, or an imported SVG icon set.
- **Don't** promote a window title bar to the page heading, or add a visible page banner alongside the hidden `PageTitle` `h1`.
- **Don't** drift back to the anti-reference: no `#f6f3ec` cream ground, no `#4c8a3f` sage accent, no Segoe UI over Georgia, no grid of equal rounded cards.
