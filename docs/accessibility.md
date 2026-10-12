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

## Keyboard focus indicator (Stage 10, ADR 0008)

Streamlit 1.65 has no focus setting. Its own ring (primary at 50% alpha) measured 2.14:1
(light) and 1.77:1 (dark) against the page. `src/mambo_explorer/focus.css` adds a 3 px solid
**#3B82F6** outline, offset 2 px, on `:focus-visible` only. Chip remove buttons get a 2 px
white outline inset 2 px instead.

**Ring contrast against the adjacent background.** Measured in Chrome, with keyboard
focus (`:focus-visible` confirmed on every control):

| Controls | Background next to the ring | Light | Dark |
|---|---|---|---|
| Buttons (primary, secondary, form submit, header, toolbar), links, expander summaries, radios, checkboxes/toggles, sliders, select box, multiselect, ERCOT/EIA viewer radio | page #FFFFFF / #0E1117 | 3.68 | 5.14 |
| Sidebar navigation links, select/multiselect chevron buttons, date-input fields | sidebar or input #F0F2F6 / #262730 | 3.28 | 4.03 |
| Chart toolbar buttons | #131720 (dark) | 3.68 (page) | 4.88 |
| Multiselect chip remove buttons (white inset ring) | chip #2563EB | 5.17 | 5.17 |

**Focused vs. unfocused.** Unfocused, the ring pixels show the adjacent background. Focused,
they are the ring color. So the change between states has the same ratios as the table.
This is a different measurement from button-text contrast, recorded separately below.

**Controls checked** (Learn, Model Labs, Explore with synthetic scratch observations, both
themes):
- sidebar links, header and menu buttons, heading anchor links, Markdown links;
- lesson-list radios, lab-choice radios, viewer source radios, exercise radios;
- bookmark and technical-detail toggles;
- 7 sliders;
- case and entity select boxes, the ERCOT series multiselect and its chip buttons;
- date-input fields;
- expanders;
- primary, secondary and form-submit buttons, and chart toolbar buttons.

Each control was focused programmatically after a keyboard event (which makes Chrome
apply `:focus-visible`). Real Tab and Shift+Tab presses were also used on Model Labs
(radios, heading links, sliders), and the ring appeared on each control reached. The
injected style adds 0 px of layout and no script.

**Stage 11 (Finance page and lesson 8).** Number inputs only recolored a thin container
border on focus, so `focus.css` now rings `stNumberInputContainer` as well. Measured on the
Finance page in both themes: number inputs 3.68 (light) / 5.14 (dark); their step buttons
3.28 / 4.03; radios, expanders, buttons, and links as above. Keyboard typing and Enter
recompute the result; the modeled-price import was completed with the keyboard. Lesson 8
and Finance have no overflow at 375 px (dark) or at 200% zoom.

## Button text and links (measured)

| Element | Theme | State | Text | Background | Ratio |
|---|---|---|---|---|---|
| Primary buttons | light and dark | default, `:active` | #FFFFFF | #2563EB | 5.17 |
| Primary buttons | light and dark | `:hover`, `:focus-visible` | #FFFFFF | #1043B1 | 8.54 |
| Secondary / Check answer | dark | default / hover / active | #FAFAFA | #131720 (+ 15% / 25% overlay) | 17.18 / 12.99 / 10.32 |
| Secondary / Check answer | light | default | #31333F | #FFFFFF | 12.53 |
| Secondary / Check answer | light | `:hover` (real pointer hover, Stage 10) | #31333F | rgba(151,166,195,0.15) over #FFFFFF | 11.14 |
| Secondary / Check answer | light | `:active` (stylesheet rule) | #31333F | rgba(151,166,195,0.25) over #FFFFFF | 10.27 |
| Markdown links (underlined) | light | — | #0054A3 | #FFFFFF | 7.51 |
| Markdown links (underlined) | dark | — | #3D9DF3 | #0E1117 | 6.58 |

Link color against surrounding body text is low (1.67:1 in light), so links rely on their
underline, which Streamlit renders in both themes.

## Zoom and narrow viewports

- **200% zoom** (a 1280 px window → 640 CSS px), checked in Model Labs with results, lesson
  6 with model runs, and Explore (EIA and ERCOT): no horizontal page scroll and no table
  wider than the viewport. The focus ring renders at 200%.
- **320 CSS px** (the reflow width, e.g. a 640 px window at 200%): no horizontal page
  scroll. Three economic-dispatch result tables (dispatch, line flows, checks) are wider
  than 320 px and scroll inside their own containers.
- **375 px**: lessons 5–7 and the lab (Stages 7–9).

## Keyboard (Stages 7–10)

Checked with the keyboard only:
- switching labs and choosing teaching cases (type to filter, Enter);
- running models (Enter on the focused button);
- answering exercises (arrow keys, Tab to **Check answer**, Enter);
- following Learn ↔ Model Labs links;
- tabbing across every control above.

## Not verified (BL-6)

1. **Screen readers.** No screen-reader session was run. Windows Narrator is present on this
   machine, but this environment cannot operate it or hear its output. NVDA and JAWS are
   not installed. The accessibility tree (names and roles) was inspected, which is not a
   substitute.
2. Data tables at 320 CSS px scroll horizontally inside their containers (the three lab
   result tables above).
3. Nothing here is a WCAG conformance claim. Only the items measured above were measured.
