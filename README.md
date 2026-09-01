# ficc-desk

A one-person, local dashboard for running a FICC trading desk routine. Rates, FX
and credit on one screen — next to the log that says whether the discipline held.

No real money: every position is paper. The output is not P&L, it is the record.

### ▶ [Open the dashboard](https://seungkeemin.github.io/)

Eight panels on a fixed grid, sized so a whole working day fits in one viewport.
The page never scrolls; only the inside of a panel does. Every number is edited in
place — click the value, type, it saves. The linked page is a static reproduction
with fixture data, and the interface is in Korean.

## What it collects

Three times a day a scheduled task pulls every field it can from three public APIs
into a local SQLite file. Whatever has no free public source is typed in by hand.

| Source | Fields | |
|---|---:|---|
| ECOS · Bank of Korea | 16 | Base rate, KOFR, CD/CP 91D, MSB 1Y, KTB 1–30Y, corporate AA-/BBB- 3Y, USD/KRW, JPY, CNY |
| FRED · St. Louis Fed | 13 | UST 3M–30Y, SOFR, fed funds upper, 10Y breakeven, US IG/HY OAS, USD/JPY, EUR/USD, VIX |
| KRX Data Marketplace | 5 | KTB futures 3/10/30Y close, open interest 3/10Y |
| Manual entry | 7 | KRW IRS 1/3/5Y, 1M NDF, 1M FX swap point, DXY, Korea 5Y CDS |
| Derived on read | 10 | Curve spreads, bond–swap, credit spreads, KR–US 10Y |
| **On screen** | **51** | 41 stored, 10 computed on read and never written |

A field stays manual until a real API call proves the endpoint. DXY is the clearest
case: it is an ICE proprietary index with no free API, and the broad dollar index on
FRED is a different number with different weights — so it is not quietly filled in
under a label that would be a lie.

## Seven rules

The dashboard is disposable; the time series is not. Breaking one of these corrupts
data quietly rather than raising an error.

1. **Missing is never zero.** No row is written, and the cell reads "not collected".
2. **Derived values are never stored.** If an input is missing the result is `None`.
3. **API specs are never guessed.** Series codes enter the config only after a real call confirms them.
4. **The observation log is append-only.** No `UPDATE`, no `DELETE`, ever.
5. **No vault file is ever deleted.** `.obsidian/` is neither read nor written.
6. **Collection failure is a normal condition.** One dead source does not kill the run.
7. **No idea without an invalidation condition.** A thesis you cannot be wrong about is not a thesis.

## Design

Not a dark theme — a discipline for information density. Zero corner radius, no
shadows, no gradients, one amber accent used by area in exactly one place: the
invalidation watch. Colour shows direction, never judgement — a rate going up is
neither good nor bad, and up-red / up-green is a setting. Nothing is gamified: the
streak is a bare number, and an empty state gives the next command, not an apology.

## Run it

Windows, Python 3.14. FastAPI · Jinja2 · SQLite (WAL) · plain JS · pytest (157).
No Node, no ORM, no build step. Migrations apply themselves on boot.

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python -m uvicorn ficc.app:app --port 8787
.venv\Scripts\python -m ficc.ingest
```

Then open `127.0.0.1:8787`. Empty keys are fine — that source is skipped and every
other one still collects, so nothing you have to sign up for is required to see the
screen.

## More

- [SPEC.md](SPEC.md) — design, and one line of justification per dependency
- [CLAUDE.md](CLAUDE.md) — operating rules and code style
- [docs/manual_fields.md](docs/manual_fields.md) — where each manual field comes from

`data/` (the SQLite file), `backups/` and `.env` are not committed. The time series
is preserved by backup files and CSV export, not by git.
