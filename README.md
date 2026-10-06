# Sisu: Local Business Lead Pipeline

Finds local businesses (dentists, plumbers, salons...) in a rotation of cities, checks their websites for problems you can fix, drops the ones that don't need you, and drafts a personalized cold email for the rest. Leads land in PostgreSQL and are worked from a Next.js dashboard.

---

## 🏗 How it works

```mermaid
flowchart TD
    A[Google Places + OpenStreetMap] -->|City + niche, chains skipped| B(Discovery)
    B -->|Skip businesses already in DB| C[Playwright scraper, shared browser, 4 at a time]
    C -->|Emails, phone, socials, site issues| D{Lead score}
    D -->|Low score, dead site, or no contact| E[Stored as disqualified, never shown]
    D -->|Worth pitching| F[Personalized email draft]
    F --> G[(PostgreSQL leads)]
    G --> H[Dashboard, sorted by score]
```

### Discovery (`discovery.py`)
- **Any city**: names in `targets.json` use their stored bounding box; anything else is geocoded with OpenStreetMap Nominatim.
- **Google Places (New) Text Search** when `GOOGLE_PLACES_API_KEY` is set: best coverage, plus phone, rating and review count. Places without a website become `no_website` leads reachable by phone.
- **OpenStreetMap (Overpass)** always, as a free fallback, with mirror failover.
- Chains/franchises (OSM `brand` tag) are skipped. Known businesses are excluded *before* the per-run limit, so each run reaches further into a city instead of returning the same first results.
- Deduplication is on a **dedupe key**: the bare domain for websites (`http://www.x.com/austin` = `x.com`), the profile path for social links, or the Google place id.

### Scraping and scoring (`extractor.py`)
Each site is loaded in a shared Chromium (waiting for JS-rendered content), then checked for:

| Issue | Weight | Pitch |
|---|---|---|
| Page shows PHP/WordPress error messages | 45 | redesign |
| No mobile viewport | 35 | redesign |
| Plain `http://` (no SSL) | 30 | redesign |
| Copyright footer 3+ years old | 25 | redesign |
| No way to book online | 20 | booking automation |
| Contact form but no booking | 15 | booking automation |
| Slow load (>5s) | 10 | |
| Missing meta description / thin text / no OpenGraph | 5 / 5 / 2 | |

Sites scoring under `MIN_LEAD_SCORE` (20), for example a modern site that already uses Calendly, ServiceTitan or similar, are **disqualified**. So are sites that fail to load and businesses with no email, phone or social profile. Disqualified businesses are stored with `status = 'disqualified'` so they are never rescraped.

Emails are pulled from `mailto:` links, page text and Cloudflare-protected addresses, filtered for placeholder/asset junk, and **checked for MX records** so dead domains don't bounce.

### Email drafts (`ai_drafter.py`)
Each email opens with the single strongest thing found on that site, something the owner can check in ten seconds ("Chrome shows a *Not secure* warning on yoursite.com", "the footer still says © 2017"). It then says why that costs them customers and makes one low-effort offer (free mockup, a 2-minute video). Every draft has a subject line and an opt-out line, plus your postal address if `SENDER_ADDRESS` is set (required for US commercial email).

Drafts are template-based by default. Set `USE_LLM_DRAFTS=true` to have Ollama reword them; output that drifts (placeholders, writing as the business, too long) is discarded in favour of the template.

---

## 🚀 Quick start (Windows)

Double-click **`start.bat`** (or run it from a terminal). It:

1. creates `.env` from `.env.example` on first run and opens it for you to fill in,
2. creates `.venv` and installs Python packages and Chromium (only when needed),
3. checks PostgreSQL is running (and tries to start its service if not),
4. creates/updates the database schema,
5. starts Ollama if `USE_LLM_DRAFTS=true`,
6. installs dashboard packages on first run, starts the dashboard on http://127.0.0.1:3000 and opens your browser.

Close the window or press Ctrl+C to stop.

### Finding leads from the dashboard

At the top of the dashboard:

- **Run**: type any city (anywhere; cities outside `targets.json` are geocoded automatically) and any business type, choose how many leads you want, and press Run. It only searches that city + niche and stops when it runs out.
- **Random**: shuffles random city/niche pairs from `targets.json` until the lead count is reached. Fill in one field to keep it fixed, e.g. city "Austin" + Random tries random niches in Austin.
- Progress, the current city/niche and the live log show while it runs; **Stop** cancels. New leads appear when it finishes.

Edit `targets.json` to change the cities and niches used by Random and the input suggestions.

---

## 📦 Requirements

- Python 3.10+, Node.js 20+, PostgreSQL 14+
- Optional: a Google Cloud API key with **Places API (New)** enabled (billed per request)
- Optional: Ollama, only if `USE_LLM_DRAFTS=true`

Manual setup (what `start.bat` automates):

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # then fill in DB_PASSWORD, SENDER_ADDRESS, GOOGLE_PLACES_API_KEY
cd dashboard && npm install && npm run dev -- -H 127.0.0.1
```

---

## 🛠 Command line

```bash
# One city + niche (any city name)
python pipeline.py --mode target --city "Boise" --niche "dentist" --quota 10

# Random city/niche pairs until 15 leads; --city or --niche keeps that one fixed
python pipeline.py --mode random --quota 15
python pipeline.py --mode random --city "Austin"

# Original fixed rotation through targets.json, remembering its position between runs
python pipeline.py
python pipeline.py --force-next     # skip to the next city/niche
python pipeline.py --reset-state    # start the rotation over

# Scrape and score a single site
python pipeline.py --test-url "https://example.com"
```

### Tests

```bash
pytest                    # offline unit tests (scoring, email cleaning, discovery, drafts)
python test_pipeline.py   # end-to-end smoke test; needs PostgreSQL and internet
```

The dashboard has no login and can start scraping runs, so keep it bound to 127.0.0.1 (as `start.bat` does).

---

## ⚖️ Sending responsibly

- Send from a separate, warmed-up domain, a few dozen emails a day at first.
- US (CAN-SPAM): include your postal address and honour opt-outs.
- Canada (CASL) and Australia (Spam Act) require consent. Business addresses published on the company's own site generally count as implied consent only when your message relates to their business role. Check before emailing those markets.
