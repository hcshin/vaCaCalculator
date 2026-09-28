# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

CLI tool that computes Cost Averaging (CA) / Value Averaging (VA) contributions across a mixed
portfolio (Korean + US equities via KIS Open API, crypto via direct exchange APIs, KRX gold spot, cash).
**USD is the base currency** for every internal calculation — KRW prices/holdings are converted with
the day's exchange rate from the Korea Eximbank API.

The README (Korean) is the authoritative spec for the report JSON schema and every field's meaning;
read it before changing report structure.

## Commands

```bash
python3 -m venv venv && source venv/bin/activate
python3 -m pip install -r pip-requirements

# print an existing report only — makes NO network calls (simple Portfolio constructor)
python3 main.py --print-report report.json

# derive the next period's report from the previous one
python3 main.py --saving-in-krw=1000000 --print-report A2402.json A2403.json

# a second KIS account needs its own secrets/tokens pair
python3 main.py --saving-in-krw=1000000 \
  --secrets-path=secrets_B.json --tokens-path=tokens_B.json \
  B2402.json B2403.json

python3 main.py --debug-level=DEBUG ...   # logs every HTTP request/response body
```

There is no test suite and no linter config. Verification is manual: run against an existing report
with `--print-report` and compare the table. Prefer the print-only (no `OUTPUT_REPORT_PATH`) form
when you just need to inspect data, since it skips all API calls.

## Architecture

**The report JSON is the state store.** There is no database: each run reads a reference report,
enriches a deep copy of it, and writes the next report. Last period's output is next period's input,
so report files form a chain. The README documents the shape of the initial (seed) report.

`main.py` (Click CLI) → `portfolio.Portfolio` (orchestration + strategy math) →
`stockwrapper.*Stock` (per-source price/holdings collection).

`Portfolio.distribute_saving()` is the pipeline, and its step order matters:

1. Dispatch each key under `stockgroups` to a handler by name — `KIS` → `KisStock`,
   `CoinGecko` → `CryptoStock` (historical key name), `KRX` → `KrxStock`, `KDB` → `KdbDepositStock`
   and `PENSION_DEPOSIT` → `PensionDepositStock` (deposits accruing interest), anything else (e.g. `OTHER`, fixed-price cash)
   → `BaseStock`. Adding a data source means adding a class and a branch here.
2. `handler.update_all()` — **each subclass overrides this and the call order inside is a hard
   contract** (holdings → prices → `_derive_appraisement` → `_update_ca_invested`); the comments
   marking the ordering are load-bearing, they encode a fixed bug (commit b4180fb).
3. Strategy: `_distribute_saving_CA` sets `need2investCA = saving * weight`; `_distribute_saving_VA`
   runs CA first, then `need2investVA = cumSumCaInvested + need2investCA - appraisement`.
4. `_derive_units_to_invest` rounds to whole units except for `CoinGecko`, which stays fractional.
5. `_derive_cum_inv_deviation` diffs the reference report's `need2invest` against holdings actually
   gained, accumulating `cum_inv_deviation`.

**`cumSumCaInvested` is an ideal trajectory, not actual money spent.** It only ever advances as
`previous cumSumCaInvested + previous need2investCA`, deliberately decoupled from real
purchases/sales (see the long commit message on 5dcd12a). Do not "fix" it to track actual
investment — that causes over-selling under VA. Real trades enter through `holdings`: for non-KIS
groups the user hand-edits `actualInvestedInUnits` into the report and `_update_holdings` folds it
into `holdings` and deletes it; KIS holdings come from the API and any `actualInvestedInUnits` there
is warned about and dropped. KIS holdings are reset to 0 before the balance query, since a fully sold
stock isn't returned by the API.

Bootstrapping (first report only): when a stock has none of `cumSumCaInvested`,
`cumSumCaInvestedInKRW`, `cumSumCaInvestedInUSD`, current appraisement is used as the seed;
the `*InKRW`/`*InUSD` variants are converted, summed, and deleted. This branch exists in both
`BaseStock._update_ca_invested` and `Portfolio._distribute_saving_CA` — keep them in sync.
All amounts in a report must be USD; a KRW figure left in `cumSumCaInvested` is silently
accepted and corrupts `need2investVA`.

`weight` is a whole-portfolio weight, not per-group; the constructor asserts the weights sum to 1.0.

## External API gotchas

- **Exchangerate (koreaexim)**: TLS requires the pinned chain in `koreaexim.pem`
  (`verify=EXCHANGERATE_CERT_PATH`, resolved relative to `portfolio.py` so any cwd works) — do not
  replace it with `verify=False`. The API returns an empty list between 00:00–11:00 KST, so
  `_get_exchange_rate` walks backwards day by day.
- **KIS tokens**: access tokens last 24h and KIS forbids re-issuing them frequently. The token file
  is read, reused while fresh, and only rewritten on expiry. One secrets/tokens pair per account —
  a report can name exactly one `accountNo`.
- **KIS rate limit**: 20 calls/sec per app key on a live account; the excess is answered with HTTP 500,
  `rt_cd` `1`, `msg_cd` `EGW00201`. Every KIS GET goes through `KisStock._kis_get`, which paces calls
  ≥0.1 s apart (class-level, shared with `KrxStock`) and retries EGW00201 up to 3 times after 1 s.
- **KIS pension/IRP accounts** are detected by `ACNT_PRDT_CD == '29'` (the suffix of `accountNo`)
  and use a different path and `tr_id`. Domestic-only.
- **KIS US prices**: a night-session `EXCD` (`NYS`/`NAS`/`AMS`) returning an empty `last` is retried
  once with the daytime code via `EXCD_NIGHT2DAY_DICT`. Both holdings and prices paginate on the
  `tr_cont` response header (`F`/`M` = continue, `D`/`E` = done).
- **KRX gold (`KrxStock`, a `KisStock` subclass)**: `data.krx.co.kr` downloads now require an
  enrolled API key, so the price of 금 99.99_1kg (KRW/g) comes from KIS `inquire-price` with the gold
  market short code `M04020000` (the dispatcher passes the KIS secrets/tokens to `KrxStock` too).
  The `M` prefix matters: `04020000` is answered with `rt_cd` `0` and a price of `0`, hence the
  `price > 0` guard. KIS `search-stock-info` does not know the gold market. The price is
  cross-checked against an unofficial Naver quote, warn-only (>1% deviation, or on failure).
  Holdings stay manual (`actualInvestedInUnits`); no balance query. Only the `GLD` stock key
  is supported.
- **Crypto (`CryptoStock`, group key `"CoinGecko"`)**: CoinGecko was dropped (its keyless tier
  rate-limits a single run to HTTP 429). The key stays `"CoinGecko"` because every existing report
  uses it. USD `price` = median of Coinbase Exchange, Kraken, Binance.US `last` prices. At least 2
  venues must answer, otherwise the run raises. KRW `priceROK` = median of Upbit, Bithumb, Coinone,
  Korbit ÷ exchange rate. It feeds only the "kimchi premium" warning (>5%), so a missing value
  is logged and skipped. A failing venue logs a warning and is skipped, and venues >2% off the
  median are warned about. Per-venue symbols live in `VENUE_SYMBS`, where a missing entry means
  the venue doesn't list the coin. Gotchas: Upbit has no KRW-BNB and 404s the *whole* request if
  any market is unknown; Kraken keys its result by internal pair names (`XBTUSD` → `XXBTZUSD`).

- **Deposits (`DepositStock` base)**: no account API, so a line accrues approximate interest into
  `accruedInterest` (in the line's currency), never into `holdings` (so `cum_inv_deviation` doesn't count it as
  investment); `appraisement` = (principal + `accruedInterest`), converted to USD. Accrual per run =
  (ref principal + ref accrued) × `_get_rate` × (1 − `INTEREST_TAX_RATE`) × days/365. Subclasses supply the rate,
  tax rate and supported currencies.
- **KDB deposit rate (`KdbDepositStock`, group key `"KDB"`, USD, 15.4% tax)**: the rate is
  the mean of KDB's posted 외화정기예금 USD 12-month resident rate on today and 91/182/273 days ago, from the
  unauthenticated `POST https://banking.kdb.co.kr/bp/CBADIE06R01.jct` with form field `_JSON_={"BSE_DT":"YYYYMMDD"}`
  (the endpoint behind the public page `CBADIE06N01.act`; the `.json`/`.act` variants return HTML). Rows are picked by
  `RATE_ROW` (`PRD_IRT_C` 600020020001, `CUR_C` USD, `IRT_KD_C` 2004 = resident, `PRD_IRT_STG_TC1` 0012000);
  the rate is `IRT_BSE_VL` in %. A weekend/holiday date returns the last effective rate (`ALY_STT_DT`); history
  goes back 4 years. Accrual needs `days` since the ref report, from the top-level `date` field that every derived
  report now carries; a ref report without it raises. VA treats interest like any other return: no path growth,
  no sell clamp (deposits can't be broken early, so acting on a sell signal is the user's call).
- **Pension deposit rate (`PensionDepositStock`, group key `"PENSION_DEPOSIT"`, KRW, no tax)**: KIS posts only the
  current month's 원리금보장 rates, as server-rendered HTML at `GET https://securities.koreainvestment.com/pension/
  nwEtcinfo/BizNotice.jsp?cmd=A_NW_32950&templetPopup=Y` (the popup variant drops the site chrome). ~300 rows in
  two tables (자사/타사제공): `<td>` 상품명, 만기, then DB, DC, IRP rates in %. The month comes from the heading
  `금리 적용일자: YYYY-MM-DD ~ …`; the page flips to next month's rates around the 28th. Each run takes the max IRP
  rate over every product and maturity, writes it into the stock's `rateHistory` (one entry per month, same month
  overwritten, latest 12 kept) and applies the mean. Parsing is regex over `<tr>`/`<td>`; it raises when the month
  heading is missing, the DB/DC/IRP header order changes, or fewer than 50 rows parse. Past months exist only as
  PDFs (`https://file.koreainvestment.com/Storage/corporate/elsrate/before3monthYYYYMM.pdf`, 3 months each, some
  months missing), used once by hand to seed a history, never parsed by the calculator.

## Conventions

- Report, secrets, and token JSON files are user data and are ignored by `*.json` in `.gitignore`.
  Never commit them — this is a public repository. Only source, README, LICENSE, `pip-requirements`,
  and `koreaexim.pem` are tracked.
- Single-quoted strings, module-level `logger = logging.getLogger('autoinvestment_logger')`,
  long lines (up to ~145 cols) are the existing style — flake8-clean but with a relaxed line limit.
- Errors are logged via `logger.error(...)` immediately before raising.
