# NWA Marketing + Library Job Tracker

Scrapes NWA public-entity job boards daily and filters for the cross-section
of **marketing/communications** and **library/MLIS** work — MLIS, library
generalist experience, circulation, reference, events, and marketing.
Dashboard only, no email.

**Dashboard:** `https://YOUR-USERNAME.github.io/YOUR-REPO-NAME/`

---

## How matching works

Jobs are scored into three tabs, checked in this order (a hard exclude wins
over everything):

1. **⭐ Marketing + Library (hybrid)** — the best matches: roles that combine
   both fields, e.g. *Outreach Librarian*, *Communications Librarian*,
   *Library Marketing Coordinator*. These are the titles most worth chasing.
2. **📚 Library** — professional library/MLIS roles: Librarian, Library
   Assistant/Associate, Circulation, Reference, Archives, Cataloging,
   Youth/Adult Services, etc.
3. **📣 Marketing & Comms** — marketing/communications/PR/events/outreach
   roles at public entities: cities, counties, schools, universities,
   museums, and regional nonprofits.

**Hard-excluded regardless of source:** generic entry-level customer service
(cashier, teller, call center, generic receptionist), pre-professional
library roles (page, shelver, library clerk/aide), trades, clinical/medical,
public safety, engineering/software, and senior executive titles (VP,
C-suite, executive director). Circulation/reference desk work at a
professional level is **not** excluded — a librarian working the desk still
counts.

Edit `HYBRID_KEYWORDS`, `LIBRARY_KEYWORDS`, `MARKETING_KEYWORDS`, and
`HARD_EXCLUDE_KEYWORDS` in `scraper.py` to tune this, then commit — the next
run picks up the change.

## Geographic scope

Northwest Arkansas core only: Fayetteville, Springdale, Rogers, Bentonville,
Bella Vista, Siloam Springs, Lowell, Centerton, Pea Ridge, Cave Springs, Elm
Springs, Tontitown, Prairie Grove, and Washington/Benton County. See
`is_valid_location()` in `scraper.py`.

## Sources (40+)

- **Public libraries:** Fayetteville Public Library, Springdale Public Library
- **Universities/colleges:** University of Arkansas (UAF), NWACC, JBU
- **Arts, museums & nonprofits:** Crystal Bridges/AWE, Scott Family Amazeum,
  Walton Arts Center, TheatreSquared, Botanical Garden of the Ozarks, The
  Jones Center, Northwest Arkansas Council
- **City & county government:** Rogers, Bentonville, Bella Vista, Lowell,
  Fayetteville, Springdale, Benton County, Washington County
- **School districts:** Bentonville, Farmington, Elkins, Greenland,
  Fayetteville, Decatur, Gravette, Gentry, Huntsville, Pea Ridge, Prairie
  Grove, Rogers, Siloam Springs, LISA Academy, Lincoln, Springdale, West
  Fork, Haas Hall Academy
- **Regional platform:** [CareersNWA](https://talent.careersnwa.com) — hosts
  many of the above employers under one job board, plus a region-wide feed
  of every Marketing & Communications posting (catches employers not
  individually configured here)
- **Aggregators:** ADP (NWA), AR State Jobs (NWA-filtered), Adzuna (optional)

Full list with live links is on the dashboard's **Sources** tab.

---

## One-Time Setup

### 1 · Create the GitHub repo
Push this folder's contents to a **public** repo (required for free GitHub
Pages).

### 2 · Enable GitHub Pages
Repo → **Settings** → **Pages** → Source: **Deploy from a branch** → Branch:
`main`, Folder: `/docs` → **Save**.

Your dashboard will be live at `https://YOUR-USERNAME.github.io/YOUR-REPO-NAME/`.

### 3 · (Optional) Add Adzuna keys for extra aggregator coverage
Register free at [developer.adzuna.com](https://developer.adzuna.com)
(250 calls/month), then add `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` as repo
secrets (**Settings → Secrets and variables → Actions**). Without these, the
scraper simply skips Adzuna and everything else still runs.

### 4 · Run it manually the first time
Repo → **Actions** tab → **Daily Job Scraper** → **Run workflow**. Takes
~5–8 minutes. When done, refresh the dashboard.

## Schedule

Runs automatically every morning at **7:00 AM CDT**. Trigger manually any
time from the Actions tab.

## Troubleshooting

- **A source returns 0 jobs every run:** the site may have changed its HTML
  structure, or genuinely has no open matching roles right now — check the
  Actions run log for that source's line.
- **CareersNWA sources return nothing:** confirm
  `https://talent.careersnwa.com/companies/<slug>` still resolves for that
  employer; slugs occasionally change if an org renames on the platform.
