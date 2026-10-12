# Accessibility record

What has been checked, how, and what is still open. These are color and keyboard checks
on specific pages. **They are not a WCAG conformance claim.** No screen-reader session has
been run.

## Theme (Stage 9)

Configuration: `.streamlit/config.toml` sets only `primaryColor = "#2563EB"` under both
`[theme.light]` and `[theme.dark]`. Defining both sections keeps the **System / Light /
Dark** choice in the app's main menu (checked in the browser: choosing Light while the OS
is dark renders the light theme). No CSS or DOM overrides are used.

Before: Streamlit's default primary `#FF4B4B` with white button text, **3.30:1**.

### Measured rendered colors (Chrome, Streamlit 1.65.0, 2026-10-11)

Ratios use the WCAG 2.x relative-luminance formula. Colors are the computed styles of the
rendered elements; hover and focus were produced with a real pointer hover and keyboard
focus (`:focus-visible` confirmed). Semi-transparent colors are composited over the
element behind them.

| Element | Theme | State | Text | Background | Ratio |
|---|---|---|---|---|---|
| Primary button ("Run this lesson's model cases", "Find the cheapest dispatch", "Run DC power flow") | light and dark | default | #FFFFFF | #2563EB | **5.17** |
| Primary button | light and dark | `:hover` | #FFFFFF | #1043B1 | **8.54** |
| Primary button | light and dark | `:focus-visible` | #FFFFFF | #1043B1 | **8.54** |
| Primary button | light and dark | `:active` (from the stylesheet rule) | #FFFFFF | #2563EB | **5.17** |
| Primary button body vs. page | light | default | — | #2563EB on #FFFFFF | 5.17 |
| Primary button body vs. page | dark | default | — | #2563EB on #0E1117 | 3.66 |
| Secondary / "Check answer" buttons | dark | default | #FAFAFA | #131720 | 17.18 |
| Secondary / "Check answer" buttons | dark | `:hover`, `:focus-visible` | #FAFAFA | rgba(172,177,195,0.15) over #131720 | 12.99 |
| Secondary / "Check answer" buttons | dark | `:active` | #FAFAFA | rgba(172,177,195,0.25) over #131720 | 10.32 |
| Focus ring (all buttons) | light | `:focus-visible` | — | rgba(37,99,235,0.5) 3.2 px over #FFFFFF | 2.14 vs. page |
| Focus ring (all buttons) | dark | `:focus-visible` | — | rgba(37,99,235,0.5) 3.2 px over #0E1117 | 1.77 vs. page |

Disabled buttons are exempt from contrast requirements and are not used on these pages.

`tests/test_theme_contrast.py` recomputes these ratios from the configuration and the
measured values, and fails if the installed Streamlit version changes (Streamlit derives
the hover shade itself, so a new version needs re-measuring).

### Not changed by the theme

- Charts use explicit colors in code (`#1f77b4`, `#d95f02`), not the primary color.
- Text, table, caption, and radio colors come from Streamlit's light/dark defaults. Stage 8
  measured them at 12.5:1 or more in the light theme.

## Keyboard (Stages 7–9)

Checked with the keyboard only: switching labs, choosing teaching cases (type to filter,
Enter), running models (Enter on the focused button), answering exercises (arrow keys, Tab
to **Check answer**, Enter), and following Learn ↔ Model Labs links.

## Narrow viewport

At 375 px there is no horizontal page scroll and no table wider than the viewport:
the economic-dispatch lab (Stage 7, dark), lessons 5–7 (Stage 8, dark), and lesson 7 with
the Stage 9 finite-change tables (light).

## Open items (BL-6)

1. **Focus ring contrast.** Streamlit's built-in ring is the primary color at 50% alpha:
   2.14:1 (light) and 1.77:1 (dark) against the page. The old default was similar (1.88 and
   2.21). Primary buttons also darken on focus, but a secondary button's focus change is a
   subtle overlay. Improving this needs CSS overrides, which this stage avoided.
2. **Light-theme secondary button hover/active** overlays were not measured.
3. **Link colors** were not measured.
4. **No screen-reader session** has been run.
