# Design standard

Every page follows this. Owner requirement (2026-10-28): the site must look designed by an expert and must
not read as AI-generated. Check new work against the "Never" list before it ships.

## Who it is for
- **Grocery shoppers** (default view): not technical, often on a phone, often older. One question:
  *what is a good buy at the store this week, and what is worth skipping?*
- **Wholesale buyers**: the trade. *Which way is each market going and what do I do about it?*

## Principles (and where they come from)
1. **Answer first, detail on demand.** The first screen answers the question; lists and charts follow.
2. **Hierarchy from size, weight and space, not boxes.** NN/g: use 2–3 clearly different type sizes; group with
   proximity (Gestalt) instead of borders. Refactoring UI: design in grayscale first, add colour last; use a fixed
   spacing scale.
3. **Familiar patterns over invention.** "Low / typical / high against past prices" (Google Flights price insight),
   stock-app watchlist rows, a two-option switch, plain tabs.
4. **Readable for everyone.** GOV.UK type scale: 19px body, 16px minimum; text contrast never lowered to
   de-emphasise (NN/g). Tap targets 44px+. Works at 375px with no sideways scroll.
5. **Colour means one thing each.** Green = good price / easing. Red = pricey / rising. Grey = typical. Sale-tag
   yellow = only the "Great price" tag. Brand leaf green for the logo and links. Always with a word and an arrow.
6. **A real identity.** A grocery shelf-tag motif (the yellow price tag), a hand-drawn tag-and-leaf mark, a
   legibility-first typeface. Nothing that could belong to any SaaS product.

## Tokens
- **Type:** Figtree, weights 400 / 600 / 700 / 800, tabular figures for prices. (Atkinson Hyperlegible was dropped on
  2026-10-28: its slashed zero read as odd in prices and years, per a reader.) Plain zero, no monospace digits.
  - Display 44/48 (phone 32/36), 800
  - Section 28/34 (phone 24/30), 800
  - Item 21/28, 700
  - Body 19/28
  - Small 16/22 (minimum for text; chart axes 14)
- **Space:** 4, 8, 16, 24, 32, 48, 64, 96. Sections are separated by 64px of space and a heading, not by cards.
- **Colour:**
  - Ink: #1b1b1b
  - Secondary text: #4a4f57 (never lighter than #5d6470)
  - Lines: #e3e1dc
  - Page: #ffffff
  - Band: #f6f3ea (one featured band per page at most)
  - Leaf: #12512f
  - Good: #12733b
  - Pricey: #b42318
  - Tag yellow: #ffd84d
  - Fair quality: #8a5a00 (quality ratings only)
- **Shape:** 6px radius on controls and tags only. No drop shadows except the active switch segment.

## Components
- **Header:** white, tag-and-leaf mark + wordmark, plain text links. Under it, the **Grocery / Wholesale** switch
  (two segments, the current one filled).
- **Search:** in the header on every page, placeholder "Search items". Scoped to the side you're on: grocery pages
  suggest grocery items only, wholesale pages wholesale only. Each suggestion: item and this week's price on the
  first line; one coloured verdict on the second ("Great price, 10% below usual"). No aisle, no old prices. Matches
  the start of words only. The list is fetched versioned so a cached copy can't mix sides. Arrow keys, Enter, Escape.
  Without JavaScript it opens /search/ (A to Z, grocery and wholesale in separate lists).
- **Aisles:** on grocery pages, Produce / Meat & poultry / Dairy & eggs tabs under the switch, the way a shopper walks the store.
- **Shelf tag:** yellow, notched like a supermarket tag, price large. Only for items that are a great price this week.
- **Price check bar:** low / typical / high zones for the same weeks in past years, with a marker for this week and
  plain labels under it.
- **Rows:** hairline-separated rows (watchlists, lists). No outer box.
- **Quality rating:** one word (Excellent / Good / Fair / Poor quality), dotted underline; the reason shows on hover
  (desktop) or tap (phone, opens in place). Never colour alone.
- **Callout:** one tinted band per page for the single most important instruction (wholesale "What to do").

## Never
- Cards around every section, cards inside cards, identical card grids, drop shadows on everything.
- Gradients, glassmorphism, glowing dark themes, emoji as icons, icons in circles above headings.
- Hero headline + row of big-number stats.
- Grey text under 16px, or grey used to push content down the hierarchy.
- Vague copy ("insights", "unlock", "at a glance"); em dashes and "X: Y" headline patterns; ranges too wide to
  act on (say the expected price; show the range only as chart shading).
- Default-looking fonts (Inter, Roboto, system UI) or a monospace font for numbers.

## Sources
- Nielsen Norman Group, *5 Principles of Visual Design in UX*: https://www.nngroup.com/articles/principles-visual-design/
- GOV.UK Design System, *Type scale*: https://design-system.service.gov.uk/styles/type-scale/
- Refactoring UI (Wathan & Schoger): hierarchy, grayscale-first, spacing scales.
- Google Flights price insights (low / typical / high against past prices): https://blog.google/products/travel/google-flights-find-deals/
- AI-design tells: https://www.925studios.co/blog/ai-slop-web-design-guide and the pixelslop pattern catalog.
- USDA SNAP-Ed *Seasonal Produce Guide* (in-season lists by season).

## Navigation (from NN/g research, 2026-10-29)
- Tabs are for parallel content of the same kind (the aisles). Anything that cuts across aisles is a plain link, never a tab.
- One row of tabs that fits a 375px phone; no overflow.
- Header links are scoped to the side of the site the reader is on.
- Seasonal promos are text links next to related content, not ad-like boxes (banner blindness).
- Lists of ideas (meals) are scannable rows: at most three short lines each (name + cost, one-line description, a tap-to-open detail). No filler like "Serves 4" for things we don't publish.
