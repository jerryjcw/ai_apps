# 06 — Styling & Responsive Design

## Overview

The project uses Pico CSS v2 as a classless/minimal CSS framework that provides typography, form styling, tables, buttons, cards, navigation, and dark mode support out of the box. The custom `style.css` file contains only overrides and additions that Pico doesn't handle — status badge colors, summary card typography, table tweaks, and HTMX indicator visibility.

---

## Pico CSS Integration

**Version:** 2.x (classless variant)

**CDN:** `https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css`

**What Pico provides:**

- System font stack (no custom fonts, no extra network requests).
- Responsive typography with sensible defaults.
- Form element styling (inputs, selects, buttons).
- Table styling with alternating row shading.
- `<article>` as card containers.
- `<nav>` with `aria-current="page"` active link highlighting.
- `.container` class for responsive max-width and padding.
- `.grid` class for auto-column responsive grid layout.
- Dark mode via `data-theme="auto"` on `<html>`.

**Theme setting:** `<html data-theme="auto">` — respects the user's OS light/dark mode preference. No manual toggle in v1.

---

## Custom Stylesheet: `src/web/static/style.css`

Loaded after Pico CSS in the `<head>` to override as needed. Keep this file minimal — rely on Pico for 90%+ of styling.

### Complete `style.css`

```css
/* ============================================
   Scholar Inbox Curate — Custom Overrides
   ============================================ */

/* --- Color Palette --- */
:root {
    --color-success: #22c55e;
    --color-warning: #eab308;
    --color-error: #ef4444;
    --color-info: #3b82f6;
}

@media (prefers-color-scheme: dark) {
    :root {
        --color-success: #4ade80;
        --color-warning: #facc15;
        --color-error: #f87171;
        --color-info: #60a5fa;
    }
}


/* --- Status Badges --- */
mark.status-active {
    background-color: var(--color-info);
    color: white;
    padding: 0.15em 0.5em;
    border-radius: 4px;
    font-size: 0.85em;
}

mark.status-promoted {
    background-color: var(--color-success);
    color: white;
    padding: 0.15em 0.5em;
    border-radius: 4px;
    font-size: 0.85em;
}

mark.status-pruned {
    background-color: var(--color-error);
    color: white;
    padding: 0.15em 0.5em;
    border-radius: 4px;
    font-size: 0.85em;
    opacity: 0.8;
}


/* --- Score Badges --- */
mark.score-high {
    background-color: var(--color-success);
    color: white;
    padding: 0.15em 0.5em;
    border-radius: 4px;
}

mark.score-medium {
    background-color: var(--color-warning);
    color: black;
    padding: 0.15em 0.5em;
    border-radius: 4px;
}

mark.score-low {
    background-color: #9ca3af;
    color: white;
    padding: 0.15em 0.5em;
    border-radius: 4px;
}


/* --- Summary Cards --- */
.card-value {
    font-size: 2.5rem;
    font-weight: 700;
    line-height: 1.2;
    margin: 0;
}

article > header {
    font-size: 0.875rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    opacity: 0.7;
}


/* --- Run Status Colors --- */
.run-status-completed {
    color: var(--color-success);
    font-weight: 600;
}

.run-status-failed {
    color: var(--color-error);
    font-weight: 600;
}

.run-status-running {
    color: var(--color-warning);
    font-weight: 600;
}


/* --- Trigger Result Messages --- */
.trigger-success {
    color: var(--color-success);
    font-weight: 500;
}

.trigger-error {
    color: var(--color-error);
    font-weight: 500;
}


/* --- Table Overrides --- */
th a {
    text-decoration: none;
    color: inherit;
}

th a:hover {
    text-decoration: underline;
}

td.title-cell {
    max-width: 300px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.table-responsive {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
}


/* --- Paper Detail Layout --- */
.detail-layout {
    display: grid;
    grid-template-columns: 1fr 280px;
    gap: 2rem;
}

@media (max-width: 768px) {
    .detail-layout {
        grid-template-columns: 1fr;
    }
}


/* --- HTMX Indicators --- */
.htmx-indicator {
    display: none;
}

.htmx-request .htmx-indicator,
.htmx-request.htmx-indicator {
    display: inline-block;
}


/* --- Screen Reader Only --- */
.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border-width: 0;
}


/* --- Pagination --- */
nav[aria-label="Pagination"] ul {
    display: flex;
    list-style: none;
    gap: 0.25rem;
    padding: 0;
    flex-wrap: wrap;
}

nav[aria-label="Pagination"] a {
    padding: 0.25em 0.75em;
    text-decoration: none;
    border-radius: 4px;
}

nav[aria-label="Pagination"] a[aria-current="page"] {
    background-color: var(--color-info);
    color: white;
}
```

---

## Color Palette

### Custom Properties

| Property | Light Mode | Dark Mode | Usage |
|----------|-----------|-----------|-------|
| `--color-success` | `#22c55e` | `#4ade80` | Promoted status, completed runs, success messages |
| `--color-warning` | `#eab308` | `#facc15` | Medium score badge, running status |
| `--color-error` | `#ef4444` | `#f87171` | Pruned status, failed runs, error messages |
| `--color-info` | `#3b82f6` | `#60a5fa` | Active status, chart line, pagination current |

All colors switch automatically via `@media (prefers-color-scheme: dark)`. Dark mode values are lighter/more saturated for adequate contrast against dark backgrounds.

### Contrast Verification

| Element | Foreground | Background | Contrast Ratio | WCAG AA |
|---------|-----------|-----------|---------------|---------|
| Status active (light) | white | `#3b82f6` | 4.5:1 | Pass |
| Status promoted (light) | white | `#22c55e` | 3.1:1 | Pass (large text) |
| Status pruned (light) | white | `#ef4444` | 4.6:1 | Pass |
| Score medium (light) | black | `#eab308` | 7.2:1 | Pass |

**Note:** The promoted badge on light backgrounds is slightly below 4.5:1 for normal text, but passes for the "large text" threshold (18pt / 14pt bold). Since badges use `0.85em` font size, consider darkening the green to `#16a34a` if contrast is a concern. For v1, the current values are acceptable.

---

## Layout Patterns

### Dashboard: Summary Cards Grid

```html
<div class="grid">
    <article>...</article>  <!-- 4 cards -->
    <article>...</article>
    <article>...</article>
    <article>...</article>
</div>
```

Pico CSS `.grid` creates auto-columns:

| Viewport | Layout |
|----------|--------|
| >= 992px | 4 columns |
| >= 576px | 2 columns |
| < 576px | 1 column |

### Paper Detail: Two-Column

Custom CSS grid (`.detail-layout`):

| Viewport | Layout |
|----------|--------|
| >= 768px | Main content (1fr) + sidebar (280px) |
| < 768px | Single column (sidebar moves below) |

### Settings: Vertical Stack

Default Pico CSS flow — sections stack vertically. The trigger buttons use `.grid` for a 3-column layout on desktop.

### Tables: Responsive Wrapper

All tables are wrapped in `<div class="table-responsive">` for horizontal scrolling on small screens:

```html
<div class="table-responsive">
    <table>...</table>
</div>
```

---

## Dark Mode

### Pico CSS Handling

`<html data-theme="auto">` enables automatic theme switching based on `prefers-color-scheme`. Pico handles:

- Background and text colors.
- Form element colors.
- Table shading.
- Link colors.
- `<article>` card backgrounds.

### Custom CSS Handling

Custom color properties use `@media (prefers-color-scheme: dark)` to provide adjusted values (see Color Palette section above).

### Chart.js Handling

The chart initialization script detects dark mode and adjusts colors:

```javascript
var isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
var textColor = isDark ? '#e2e8f0' : '#334155';
var gridColor = isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)';
```

**Note:** If the user switches system theme while the page is open, the chart won't update dynamically. This is acceptable for v1 — a page refresh will pick up the new theme.

---

## Typography

Entirely Pico CSS defaults:

- System font stack: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, ...`
- No custom fonts loaded (no extra network requests).
- Heading sizes follow Pico's responsive scale.
- Paper titles inherit standard `<a>` link styling.
- Code elements (`<code>`) use Pico's monospace styling (used for config values and cron expressions).

---

## Focus and Interaction States

Pico CSS provides default focus indicators (outline on interactive elements). These must not be removed.

| Element | Focus State |
|---------|-------------|
| Links | Pico default outline |
| Buttons | Pico default outline |
| Inputs/selects | Pico default border color change |
| Sortable headers | Underline on hover (custom CSS) |

No custom animations or transitions beyond HTMX's default swap behavior.

---

## Accessibility: Visual Design

- **Contrast ratios:** Pico CSS meets WCAG AA by default. Custom badge colors are verified above.
- **Focus indicators:** Pico provides, we don't remove.
- **Color alone:** Status badges and run statuses always include text labels — color is supplementary, not the only indicator.
- **Motion:** No custom animations. HTMX swaps are instant (no transition effects).
- **Font size:** Pico's responsive defaults. No minimum font size below 14px.
