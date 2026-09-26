# Price normalization rules

Code: `pipeline/normalize.py`. Every stored row keeps the prices exactly as USDA reported them; the normalized columns are derived and can be recomputed.

## Columns

| Column | Meaning |
|---|---|
| `low_price`, `high_price` | USDA range for the day, per package (produce), per cwt (beef), cents/lb (chicken), or per retail unit. |
| `mostly_low_price`, `mostly_high_price` | USDA "mostly" range, when given (where most trading happened). |
| `unit_price` | One representative price: **midpoint of the "mostly" range if present, otherwise midpoint of low/high.** Retail: weighted average advertised price. Beef: weighted average. Chicken: weighted average. |
| `price_unit` | Unit of `unit_price`: `$/package`, `$/cwt`, `cents/lb`, `$/each`, `$/per lb`, `$/3 lb bag` ... |
| `normalized_price`, `normalized_unit` | `unit_price` converted to **dollars per lb** or **dollars per each**. Blank when we can't convert reliably. |

## Rules (in order)

1. **Per each for count-packed items people buy by the piece**: avocados, iceberg, romaine. `unit_price ÷ count`. Count comes from the size (`48s` → 48, `24s film wrapped` → 24) or the pack (`12 3-count packages` → 36).
2. **Per lb when the package weight is known**: parsed from the package text:
   - `25 lb cartons`, `50 lb sacks` → 25, 50
   - `5 kg/11 lb cartons` → 11 (uses the lb figure)
   - `4 kg cartons` → 4 × 2.20462
   - `8 1-lb containers` → 8; `16 3-lb mesh sacks` → 48; `12 10-oz containers` → 7.5
   - `12 1-pint baskets` → 12 × **0.75 lb per pint (assumption)**
3. **Container weights not in the text — ASSUMPTIONS, please review:**
   - Bell peppers, `1 1/9 bushel cartons` (incl. place pack): **25 lb**
   - Tomatoes, `cartons 2 layer`: **20 lb**
   - Avocados, `cartons 2 layer`: **25 lb** (only used if no count is given)
   - Cucumbers, `1 1/9 bushel cartons`: **55 lb**
4. **Otherwise per each if a count is known**, else blank.
5. **Beef**: $/cwt ÷ 100 → $/lb. **Chicken**: cents/lb ÷ 100 → $/lb.
6. **Retail**: `each` and `per lb` pass through; bag sizes (`3 lb bag`) are divided by their weight; other units (e.g. `4 count mesh bags`) are left blank for now.

Counts in dozens (celery `2 dozen`, `2 1/2 dozen`) become 24 and 30. Retail single packs (`18 oz package`) are converted by weight.

Rows graded "Fair Appearance", "Fair Condition" and similar are distressed product (e.g. NY strawberries at $5/flat next to $37 for fine fruit). They're stored, but headline series should exclude them.

Tomato sizes like `4x5s` or `5x6 size` describe layer patterns, not counts, so they're never used as a count.

## Known gaps
- Lettuce cartons with no count, bushel containers for other commodities, and "flats" without a weight are left blank until we add verified weights.
- Weights are nominal pack weights, not actual fill.
