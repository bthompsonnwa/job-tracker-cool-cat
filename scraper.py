#!/usr/bin/env python3
"""
NWA Marketing + Library Job Tracker
Cross-section of marketing/communications and library/MLIS roles at
public entities (cities, counties, schools, universities, libraries,
museums, and regional nonprofits) in Northwest Arkansas.
Dashboard only (no email) — updates docs/jobs.json for GitHub Pages.
"""

import requests
from bs4 import BeautifulSoup
import json, os, hashlib, logging, re, time
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

JOBS_FILE      = "docs/jobs.json"
ADZUNA_APP_ID  = os.environ.get("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# ──────────────────────────────────────────────────────────────────────────────
# GEOGRAPHIC FILTER — NWA core only
# ──────────────────────────────────────────────────────────────────────────────

UNAMBIGUOUS_CITIES = [
    "bentonville", "bella vista", "siloam springs", "cave springs",
    "elm springs", "pea ridge", "tontitown", "prairie grove",
    "northwest arkansas", "nwa",
]
AMBIGUOUS_AR = [
    "rogers", "lowell", "centerton", "gravette", "highfill", "gentry",
    "fayetteville", "springdale", "west fork", "elkins", "greenland",
    "johnson", "farmington", "lincoln", "goshen",
    "benton county", "washington county",
]
_AR_PAT = re.compile(r"\b(ar|ark|arkansas)\b", re.I)


def is_valid_location(loc: str) -> bool:
    """True if blank/unknown, an unambiguous NWA city, or an ambiguous city
    qualified with an AR/Arkansas marker."""
    if not loc or not loc.strip():
        return True
    l = loc.lower()
    if "little rock" in l:
        return False
    for city in UNAMBIGUOUS_CITIES:
        if city in l:
            return True
    if _AR_PAT.search(l):
        for city in AMBIGUOUS_AR:
            if city in l:
                return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# KEYWORD FILTERS
# ──────────────────────────────────────────────────────────────────────────────

def _kw_match(keyword, text):
    """Word-boundary keyword match to avoid substring false positives."""
    kw = keyword.strip()
    return bool(re.search(r'(?<![a-z])' + re.escape(kw) + r'(?![a-z])', text))


# Cross-section titles — marketing/comms work *inside* a library, or library
# work with an explicit outreach/marketing/PR bent. Highest-value matches.
# e.g. "Outreach Librarian (Open Rank)" @ University of Arkansas Libraries.
HYBRID_KEYWORDS = [
    "outreach librarian", "marketing librarian", "communications librarian",
    "library marketing", "library communications", "library outreach",
    "library public relations", "public relations librarian",
    "engagement librarian", "digital marketing librarian", "social media librarian",
    "marketing and outreach librarian", "communications and outreach librarian",
    "development and communications librarian", "development and marketing librarian",
    "library programming and outreach", "brand librarian",
    "public services and outreach librarian", "instruction and outreach librarian",
    "community engagement librarian", "outreach and engagement librarian",
    "academic outreach", "experiential learning librarian",
]

# Library / MLIS / archives — professional-level, not pre-professional
# (shelving/paging roles are excluded separately below).
LIBRARY_KEYWORDS = [
    "librarian", "library assistant", "library associate", "library technician",
    "library specialist", "library coordinator", "library manager", "library director",
    "branch librarian",
    "circulation supervisor", "circulation manager", "circulation coordinator",
    "circulation assistant", "circulation librarian",
    "reference librarian", "reference and instruction", "reference desk",
    "youth services librarian", "children's librarian", "childrens librarian",
    "teen librarian", "adult services librarian", "adult services coordinator",
    "bookmobile", "interlibrary loan",
    "cataloging librarian", "cataloger", "archivist", "archives",
    "special collections", "acquisitions librarian", "instruction librarian",
    "research librarian", "digital services librarian", "systems librarian",
    "electronic resources librarian",
    "library services coordinator", "public services librarian",
    "library program coordinator", "business librarian", "rare books",
]

# Marketing / communications / PR / events / outreach at public-facing entities.
MARKETING_KEYWORDS = [
    "marketing coordinator", "marketing specialist", "marketing manager",
    "marketing director", "marketing assistant", "marketing and communications",
    "marketing & communications", "marketing and events coordinator",
    "communications coordinator", "communications specialist", "communications manager",
    "communications director", "communications assistant",
    "public information officer", "public relations coordinator",
    "public relations specialist", "public relations manager", "media relations",
    "content coordinator", "content specialist", "content creator",
    "content marketing", "content manager",
    "social media coordinator", "social media specialist", "social media manager",
    "digital marketing", "brand coordinator", "brand specialist", "brand manager",
    "creative services coordinator", "publications coordinator", "publications specialist",
    "graphic designer", "graphic design coordinator", "web content coordinator",
    "engagement coordinator", "community engagement coordinator",
    "community outreach coordinator", "outreach coordinator", "outreach specialist",
    "outreach manager", "events specialist",
    "special events coordinator", "event manager", "events manager",
    "programming coordinator", "public programs coordinator",
    "volunteer coordinator", "development and communications", "membership and marketing",
    "donor relations coordinator", "member engagement coordinator",
    "visitor services manager", "visitor services coordinator", "guest experience manager",
]

# Hard excludes — word-boundary matched. Filters out generic/entry-level
# customer service and fields entirely outside this candidate's background,
# without excluding library roles just because they involve desk work.
HARD_EXCLUDE_KEYWORDS = [
    # Pre-professional / entry-level library & clerical
    "library page", "shelver", "library clerk", "circulation clerk", "library aide",
    "office clerk", "file clerk", "data entry clerk", "data entry",
    # K-12 school library roles — require an Arkansas teaching license, which
    # this candidate doesn't have (see also the school-source filter in
    # scrape_all(), which catches these even under a bare "Librarian" title)
    "library media specialist", "school librarian", "teacher librarian", "teacher-librarian",
    # Generic customer service / retail / call center
    "cashier", "retail associate", "retail sales", "sales associate",
    "sales representative", "account executive", "call center", "call-center",
    "contact center", "bank teller", "teller", "customer service representative",
    "customer service associate", "customer service rep", "front desk agent",
    "hotel front desk", "receptionist",
    # Logistics / trades / manual labor
    "truck driver", "cdl driver", "delivery driver", "warehouse associate",
    "warehouse worker", "forklift", "picker", "packer", "material handler",
    "dock worker", "custodian", "custodial", "janitor", "groundskeeper",
    "maintenance mechanic", "hvac technician", "electrician", "plumber",
    "food service", "cafeteria",
    # Clinical / medical
    "registered nurse", "school nurse", "lpn", "cna", "nurse practitioner",
    "physician", "pharmacist", "physical therapist", "occupational therapist",
    "phlebotomist", "paramedic", "emt", "dietitian", "dietician",
    # Public safety
    "police officer", "firefighter", "dispatcher", "bus driver", "bus monitor", "911",
    # Technical / engineering
    "software engineer", "software developer", "web developer", "devops",
    "network engineer", "cybersecurity", "data scientist", "machine learning",
    "electrical engineer", "mechanical engineer", "civil engineer",
    # Finance / accounting
    "accountant", "bookkeeper", "accounts payable", "financial analyst", "loan officer",
    # Senior / executive — too senior for this candidate's stage
    "vice president", "chief marketing officer", "chief communications officer",
    "chief", "cto", "cfo", "ceo", "coo", "superintendent",
    "regional manager", "district manager", "general manager", "store manager",
    "executive director", "senior director",
    # Fields/attributes explicitly out of scope for this candidate
    "agriculture", "internship", "intern", "trade coordinator", "trades coordinator",
    "apprenticeship", "remote",
]


def categorize(title, extra=""):
    """Returns (category, match_reason) or (None, reason).
    HYBRID > LIBRARY > MARKETING priority; hard excludes checked first."""
    combined = (title + " " + extra).lower()
    for kw in HARD_EXCLUDE_KEYWORDS:
        if _kw_match(kw, combined):
            return None, f"excluded:{kw.strip()}"
    for kw in HYBRID_KEYWORDS:
        if _kw_match(kw, combined):
            return "hybrid", kw
    for kw in LIBRARY_KEYWORDS:
        if _kw_match(kw, combined):
            return "library", kw
    for kw in MARKETING_KEYWORDS:
        if _kw_match(kw, combined):
            return "marketing", kw
    return None, "no_match"


# ──────────────────────────────────────────────────────────────────────────────
# SOURCE CONFIG
# ──────────────────────────────────────────────────────────────────────────────

APPLITRACK_DISTRICTS = [
    {"id": "bentonville", "name": "Bentonville SD",
     "list_url": "https://www.applitrack.com/bentonville/onlineapp/default.aspx?all=1"},
    {"id": "farmcards",   "name": "Farmington SD",
     "list_url": "https://www.applitrack.com/farmcards/onlineapp/jobpostings/view.asp?internaltransferform.Url=&all=1"},
]

TEDK12_DISTRICTS = [
    {"name": "Elkins SD",                    "url": "https://elkinsdistrict.tedk12.com/hire/index.aspx"},
    {"name": "Greenland SD",                 "url": "https://greenlandschools.tedk12.com/hire/index.aspx"},
    {"name": "Fayetteville Public Schools",  "url": "https://district.tedk12.com/hire/index.aspx"},
]

SCHOOLSPRING_DISTRICTS = [
    {"subdomain": "decatursd",     "name": "Decatur SD"},
    {"subdomain": "gravette",      "name": "Gravette SD"},
    {"subdomain": "gentry",        "name": "Gentry SD"},
    {"subdomain": "hsd",           "name": "Huntsville SD"},
    {"subdomain": "pearidge",      "name": "Pea Ridge SD"},
    {"subdomain": "pgtigers",      "name": "Prairie Grove SD"},
    {"subdomain": "rogersschools", "name": "Rogers SD"},
    {"subdomain": "siloamschools", "name": "Siloam Springs SD"},
    {"subdomain": "lisaacademy",   "name": "LISA Academy"},
]

WORKDAY_SOURCES = [
    {"name": "University of Arkansas (UAF)", "location": "Fayetteville, AR",
     "api_url":  "https://uasys.wd5.myworkdayjobs.com/wday/cxs/uasys/UAF_External_Career_Site/jobs",
     "base_url": "https://uasys.wd5.myworkdayjobs.com/en-US/UAF_External_Career_Site"},
    {"name": "NWACC", "location": "Bentonville, AR",
     "api_url":  "https://nwacc.wd1.myworkdayjobs.com/wday/cxs/nwacc/NWACC_External_Career_Site/jobs",
     "base_url": "https://nwacc.wd1.myworkdayjobs.com/en-US/NWACC_External_Career_Site"},
    {"name": "Crystal Bridges / AWE", "location": "Bentonville, AR",
     "api_url":  "https://awe.wd1.myworkdayjobs.com/wday/cxs/awe/Art_and_Wellness/jobs",
     "base_url": "https://awe.wd1.myworkdayjobs.com/en-US/Art_and_Wellness"},
]

# Northwest Arkansas' regional job board — hosts many local public/nonprofit
# employers under one platform. Confirmed live (user-supplied example posting:
# "Outreach Librarian (Open Rank)" @ University of Arkansas via this exact site).
CAREERSNWA_SOURCES = [
    {"name": "University of Arkansas (CareersNWA)",
     "url": "https://talent.careersnwa.com/companies/university-of-arkansas",
     "location": "Fayetteville, AR"},
    {"name": "NWACC (CareersNWA)",
     "url": "https://talent.careersnwa.com/companies/northwest-arkansas-community-college",
     "location": "Bentonville, AR"},
    {"name": "City of Fayetteville",
     "url": "https://talent.careersnwa.com/companies/city-of-fayetteville",
     "location": "Fayetteville, AR"},
    {"name": "City of Springdale",
     "url": "https://talent.careersnwa.com/companies/city-of-springdale",
     "location": "Springdale, AR"},
    {"name": "City of Bentonville",
     "url": "https://talent.careersnwa.com/companies/city-of-bentonville",
     "location": "Bentonville, AR"},
    {"name": "Benton County Government",
     "url": "https://talent.careersnwa.com/companies/benton-county-government",
     "location": "Bentonville, AR"},
    {"name": "The Jones Center",
     "url": "https://talent.careersnwa.com/companies/the-jones-center",
     "location": "Springdale, AR"},
    {"name": "TheatreSquared",
     "url": "https://talent.careersnwa.com/companies/theatresquared",
     "location": "Fayetteville, AR"},
    {"name": "Northwest Arkansas Council",
     "url": "https://talent.careersnwa.com/companies/northwest-arkansas-council",
     "location": "Springdale, AR"},
    {"name": "Botanical Garden of the Ozarks",
     "url": "https://talent.careersnwa.com/companies/botanical-garden-of-the-ozarks-2",
     "location": "Fayetteville, AR"},
    {"name": "Scott Family Amazeum",
     "url": "https://talent.careersnwa.com/companies/scott-family-amazeum",
     "location": "Bentonville, AR"},
]

# Regional feed of every Marketing & Communications posting across all
# employers on the CareersNWA platform — catches employers not hardcoded above.
CAREERSNWA_REGIONAL_FEED = (
    "https://talent.careersnwa.com/jobs"
    "?filter=eyJqb2JfZnVuY3Rpb25zIjpbIk1hcmtldGluZyAmIENvbW11bmljYXRpb25zIl19"
)

# Full display list for the dashboard's Sources tab (kept in sync with scrape_all()).
ALL_SOURCES = [
    {"name": "Bentonville SD",         "url": "https://www.applitrack.com/bentonville/onlineapp/default.aspx?all=1", "type": "school"},
    {"name": "Farmington SD",          "url": "https://www.applitrack.com/farmcards/onlineapp/jobpostings/view.asp?all=1", "type": "school"},
    {"name": "Elkins SD",              "url": "https://elkinsdistrict.tedk12.com/hire/index.aspx", "type": "school"},
    {"name": "Greenland SD",           "url": "https://greenlandschools.tedk12.com/hire/index.aspx", "type": "school"},
    {"name": "Fayetteville Public Schools", "url": "https://district.tedk12.com/hire/index.aspx", "type": "school"},
    {"name": "Decatur SD",             "url": "https://decatursd.schoolspring.com/", "type": "school"},
    {"name": "Gravette SD",            "url": "https://gravette.schoolspring.com/", "type": "school"},
    {"name": "Gentry SD",              "url": "https://gentry.schoolspring.com/", "type": "school"},
    {"name": "Huntsville SD",          "url": "https://hsd.schoolspring.com/", "type": "school"},
    {"name": "Pea Ridge SD",           "url": "https://pearidge.schoolspring.com/", "type": "school"},
    {"name": "Prairie Grove SD",       "url": "https://pgtigers.schoolspring.com/", "type": "school"},
    {"name": "Rogers SD",              "url": "https://rogersschools.schoolspring.com/", "type": "school"},
    {"name": "Siloam Springs SD",      "url": "https://siloamschools.schoolspring.com/", "type": "school"},
    {"name": "LISA Academy",           "url": "https://lisaacademy.schoolspring.com/", "type": "school"},
    {"name": "Lincoln Consolidated SD","url": "https://careers.smartrecruiters.com/Lincoln2", "type": "school"},
    {"name": "Springdale SD",          "url": "https://apply.sdale.org/winocular/workspace/wSpace.exe?Action=wsJobsMain", "type": "school"},
    {"name": "West Fork SD",           "url": "https://flowpoint.wftigers.org/careers/opportunities/", "type": "school"},
    {"name": "Haas Hall Academy",      "url": "https://haashall.org/welcome__trashed/employment/", "type": "school"},
    {"name": "Rogers (City)",          "url": "https://www.rogersar.gov/Jobs.aspx", "type": "government"},
    {"name": "City of Bella Vista",    "url": "https://recruiting.paylocity.com/recruiting/jobs/All/b1e8c19e-977f-41ec-89e7-a138ab6e72eb/City-of-Bella-Vista", "type": "government"},
    {"name": "Lowell (City)",          "url": "https://www.lowellarkansas.gov/jobs", "type": "government"},
    {"name": "Washington County AR",   "url": "https://www.washingtoncountyar.gov/government/departments-f-z/human-resources/job-postings", "type": "government"},
    {"name": "Springdale Public Library", "url": "https://springdalelibrary.org/employment/", "type": "library"},
    {"name": "Fayetteville Public Library", "url": "https://www.faylib.org/work-8103", "type": "library"},
    {"name": "Walton Arts Center",     "url": "https://waltonartscenter.org/about/employment/", "type": "arts_nonprofit"},
    {"name": "University of Arkansas (UAF)", "url": "https://uasys.wd5.myworkdayjobs.com/UAF_External_Career_Site", "type": "university"},
    {"name": "NWACC",                  "url": "https://nwacc.wd1.myworkdayjobs.com/NWACC_External_Career_Site", "type": "university"},
    {"name": "Crystal Bridges / AWE",  "url": "https://awe.wd1.myworkdayjobs.com/Art_and_Wellness", "type": "arts_nonprofit"},
    {"name": "JBU (Staff)",            "url": "https://www.jbu.edu/human-resources/staff-job-listings/", "type": "university"},
    {"name": "JBU (Faculty)",          "url": "https://www.jbu.edu/human-resources/faculty-job-listings/", "type": "university"},
    {"name": "ADP (NWA)",              "url": "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?cid=a75698d1-4927-42e2-8b24-4b1e4d60fa54", "type": "aggregator"},
    {"name": "AR State Jobs (NWA)",    "url": "https://arcareers.arkansas.gov/search/?searchby=location&q=&locationsearch=northwest+arkansas", "type": "aggregator"},
] + [
    {"name": s["name"], "url": s["url"], "type": "university" if "University" in s["name"] or "NWACC" in s["name"]
        else "government" if any(x in s["name"] for x in ["City of", "County"])
        else "arts_nonprofit"}
    for s in CAREERSNWA_SOURCES
] + [{"name": "CareersNWA Regional Feed (Marketing & Comms)", "url": CAREERSNWA_REGIONAL_FEED, "type": "aggregator"}]

# ──────────────────────────────────────────────────────────────────────────────
# GENRE CLASSIFICATION — Education / Community / Commercial
#
# Fixed sources (schools, universities, libraries, government, arts/nonprofits)
# are classified from their known type. Dynamic per-job employers (from the
# CareersNWA regional feed, ADP, Adzuna, AR State Jobs) are classified by a
# keyword heuristic on the employer name; anything that doesn't look like a
# public/nonprofit/education entity defaults to "commercial".
# ──────────────────────────────────────────────────────────────────────────────

SOURCE_TYPE_BY_NAME = {s["name"]: s["type"] for s in ALL_SOURCES}

_EDUCATION_NAME_HINTS = [
    "university", "college", " sd", "school district", "public schools",
    "academy", "elementary", "middle school", "high school",
]
_COMMUNITY_NAME_HINTS = [
    "city of", "county", "public library", "library", "museum", "arts center",
    "theatre", "theater", "botanical garden", "council", "town of", "state jobs",
]


def classify_genre(district):
    src_type = SOURCE_TYPE_BY_NAME.get(district)
    if src_type in ("school", "university"):
        return "education"
    if src_type in ("library", "government", "arts_nonprofit"):
        return "community"
    d = district.lower()
    if any(h in d for h in _EDUCATION_NAME_HINTS):
        return "education"
    if any(h in d for h in _COMMUNITY_NAME_HINTS):
        return "community"
    return "commercial"


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def make_id(source, title, url=""):
    return hashlib.md5(f"{source}|{title}|{url}".encode()).hexdigest()[:12]


def make_job(source, title, url, platform, category="marketing",
             location="", posted="", match_reason=""):
    return {
        "id":           make_id(source, title, url),
        "title":        title,
        "district":     source,
        "location":     location,
        "url":          url,
        "platform":     platform,
        "category":     category,
        "genre":        classify_genre(source),
        "match_reason": match_reason,
        "posted_date":  posted,
        "first_seen":   datetime.now().strftime("%Y-%m-%d"),
    }


def load_jobs():
    if os.path.exists(JOBS_FILE):
        with open(JOBS_FILE) as f:
            return json.load(f)
    return {"last_updated": None, "jobs": [], "sources": []}


def save_jobs(data):
    os.makedirs("docs", exist_ok=True)
    with open(JOBS_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)
    log.info(f"Saved {len(data['jobs'])} jobs to {JOBS_FILE}")


def _safe(fn, *args, label=None, pause=1, **kwargs):
    """Run one scraper; a crash logs an error instead of killing the whole run."""
    name = label or getattr(fn, "__name__", "scraper")
    try:
        result = fn(*args, **kwargs) or []
    except Exception as e:
        log.error(f"{name} CRASHED: {e}")
        result = []
    time.sleep(pause)
    return result


def pw_get_soup(url, wait=4):
    """Shared Playwright helper for JS-rendered pages."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log.warning("Playwright not installed")
        return None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                ctx  = browser.new_context(user_agent=HEADERS["User-Agent"])
                page = ctx.new_page()
                try:
                    page.goto(url, wait_until="networkidle", timeout=40000)
                except PWTimeout:
                    page.wait_for_timeout(5000)
                time.sleep(wait)
                html = page.content()
            finally:
                browser.close()
        return BeautifulSoup(html, "html.parser")
    except Exception as e:
        log.error(f"Playwright error on {url}: {e}")
        return None


def scrape_links(soup, name, base, platform, location="",
                  href_words=None, title_skip=None):
    """Generic link-based scraper core shared by simple HTML sources."""
    jobs, added = [], set()
    href_words = href_words or ["job", "career", "position", "posting", "opportunity", "req"]
    title_skip = title_skip or ["home", "about", "contact", "login", "search",
                                 "department", "more info", "apply now", "back to"]
    for a in soup.find_all("a", href=True):
        href  = a["href"]
        title = a.get_text(strip=True)
        if not title or len(title) < 5 or href in added:
            continue
        if not any(w in href.lower() for w in href_words):
            continue
        if any(x in title.lower() for x in title_skip):
            continue
        added.add(href)
        full_url = href if href.startswith("http") else base.rstrip("/") + (href if href.startswith("/") else "/" + href)
        cat, reason = categorize(title)
        if cat:
            jobs.append(make_job(name, title, full_url, platform,
                                  category=cat, location=location, match_reason=reason))
    return jobs


# ──────────────────────────────────────────────────────────────────────────────
# SCHOOL DISTRICT SCRAPERS
# ──────────────────────────────────────────────────────────────────────────────

def scrape_applitrack(district):
    name, list_url, did = district["name"], district["list_url"], district["id"]
    jobs = []
    xml_url = f"https://www.applitrack.com/{did}/onlineapp/JobPostingFeed.aspx"
    try:
        r = requests.get(xml_url, headers=HEADERS, timeout=15)
        if r.status_code == 200 and "<item>" in r.text:
            soup = BeautifulSoup(r.text, "xml")
            for item in soup.find_all("item"):
                title = (item.find("title").text or "").strip()
                url   = (item.find("link").text or list_url).strip()
                desc  = (item.find("description").text or "").strip()
                cat, reason = categorize(title, desc)
                if cat:
                    jobs.append(make_job(name, title, url, "AppliTrack", category=cat, match_reason=reason))
            log.info(f"{name}: {len(jobs)} jobs (XML)")
            return jobs
    except Exception as e:
        log.warning(f"{name} XML: {e}")
    try:
        r    = requests.get(list_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not any(x in href for x in ["JobDetails", "ViewJob", "jobpostings"]):
                continue
            title = a.get_text(strip=True)
            if not title or len(title) < 4:
                continue
            full_url = href if href.startswith("http") else f"https://www.applitrack.com{href}"
            cat, reason = categorize(title)
            if cat:
                jobs.append(make_job(name, title, full_url, "AppliTrack", category=cat, match_reason=reason))
        log.info(f"{name}: {len(jobs)} jobs (HTML)")
    except Exception as e:
        log.error(f"{name}: {e}")
    return jobs


def scrape_tedk12(district):
    name, base_url = district["name"], district["url"]
    jobs = []
    try:
        r    = requests.get(base_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=re.compile(r"ViewJob\.aspx")):
            title    = a.get_text(strip=True)
            href     = a["href"]
            full_url = href if href.startswith("http") else base_url.rsplit("/", 1)[0] + "/" + href.lstrip("/")
            row      = a.find_parent("tr")
            cells    = row.find_all("td") if row else []
            posted   = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            location = cells[3].get_text(strip=True) if len(cells) > 3 else ""
            cat, reason = categorize(title)
            if cat:
                jobs.append(make_job(name, title, full_url, "PowerSchool",
                                      category=cat, location=location, posted=posted, match_reason=reason))
        log.info(f"{name}: {len(jobs)} jobs")
    except Exception as e:
        log.error(f"{name}: {e}")
    return jobs


def scrape_smartrecruiters():
    name = "Lincoln Consolidated SD"
    url  = "https://careers.smartrecruiters.com/Lincoln2"
    jobs = []
    try:
        r    = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=re.compile(r"jobs\.smartrecruiters\.com")):
            el    = a.find(["h4", "h3", "h2", "strong"])
            title = el.get_text(strip=True) if el else a.get_text(strip=True)
            if not title:
                continue
            cat, reason = categorize(title)
            if cat:
                jobs.append(make_job(name, title, a["href"], "SmartRecruiters",
                                      category=cat, location="Lincoln, AR", match_reason=reason))
        log.info(f"{name}: {len(jobs)} jobs")
    except Exception as e:
        log.error(f"{name}: {e}")
    return jobs


def scrape_springdale_sd():
    name = "Springdale SD"
    url  = "https://apply.sdale.org/winocular/workspace/wSpace.exe?Action=wsJobsMain"
    jobs = []
    try:
        r    = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=re.compile(r"ViewJobPosting")):
            title = a.get_text(strip=True)
            if not title:
                continue
            m   = re.search(r"ViewJobPosting\('(\w+)'", a["href"])
            pid = m.group(1) if m else ""
            job_url = (f"https://apply.sdale.org/winocular/workspace/wSpace.exe"
                       f"?Action=wsViewPosting&postingID={pid}") if pid else url
            row   = a.find_parent("tr")
            cells = row.find_all("td") if row else []
            jtype  = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            posted = cells[4].get_text(strip=True) if len(cells) > 4 else ""
            loc    = cells[7].get_text(strip=True) if len(cells) > 7 else ""
            if posted and not re.search(r"\d{1,2}/\d{1,2}/\d{4}", posted):
                posted = ""
            cat, reason = categorize(title, jtype)
            if cat:
                jobs.append(make_job(name, title, job_url, "WinOcular",
                                      category=cat, location=loc, posted=posted, match_reason=reason))
        log.info(f"{name}: {len(jobs)} jobs")
    except Exception as e:
        log.error(f"{name}: {e}")
    return jobs


def scrape_westfork():
    name = "West Fork SD"
    url  = "https://flowpoint.wftigers.org/careers/opportunities/"
    jobs = []
    try:
        r    = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        seen = set()
        for a in soup.find_all("a", href=re.compile(r"/careers/opportunities/entry/")):
            title = a.get_text(strip=True)
            if not title:
                parent = a.find_parent(["h2", "h3", "h4"])
                title  = parent.get_text(strip=True) if parent else ""
            if not title or title in seen:
                continue
            seen.add(title)
            full_url = a["href"] if a["href"].startswith("http") else "https://flowpoint.wftigers.org" + a["href"]
            cat, reason = categorize(title)
            if cat:
                jobs.append(make_job(name, title, full_url, "FlowPoint",
                                      category=cat, location="West Fork, AR", match_reason=reason))
        log.info(f"{name}: {len(jobs)} jobs")
    except Exception as e:
        log.error(f"{name}: {e}")
    return jobs


def scrape_schoolspring(district):
    name = district["name"]
    sub  = district["subdomain"]
    url  = f"https://{sub}.schoolspring.com/"
    jobs = []
    soup = pw_get_soup(url, wait=3)
    if not soup:
        return jobs
    added = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        is_job = "/job/" in href or "jobID" in href.lower() or "job-listing" in href
        if not is_job or not text or len(text) < 5 or href in added:
            continue
        added.add(href)
        full_url = href if href.startswith("http") else f"https://{sub}.schoolspring.com{href}"
        cat, reason = categorize(text)
        if cat:
            jobs.append(make_job(name, text, full_url, "SchoolSpring", category=cat, match_reason=reason))
    log.info(f"{name}: {len(jobs)} jobs")
    return jobs


def scrape_haashall():
    name = "Haas Hall Academy"
    url  = "https://haashall.org/welcome__trashed/employment/"
    jobs = []
    try:
        r       = requests.get(url, headers=HEADERS, timeout=15)
        soup    = BeautifulSoup(r.text, "html.parser")
        content = soup.find("main") or soup.find(class_=re.compile(r"entry|content|post", re.I)) or soup
        if any(x in content.get_text().lower() for x in ["no open", "no current", "no position"]):
            log.info(f"{name}: no open positions")
            return jobs
        for a in content.find_all("a", href=True):
            title = a.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            href = a["href"]
            if any(x in href for x in ["#", "mailto", "tel:", "facebook", "twitter", "instagram"]):
                continue
            cat, reason = categorize(title)
            if cat:
                full_url = href if href.startswith("http") else "https://haashall.org" + href
                jobs.append(make_job(name, title, full_url, "WordPress",
                                      category=cat, match_reason=reason))
        log.info(f"{name}: {len(jobs)} jobs")
    except Exception as e:
        log.error(f"{name}: {e}")
    return jobs


# ──────────────────────────────────────────────────────────────────────────────
# GOVERNMENT / COUNTY SCRAPERS
# ──────────────────────────────────────────────────────────────────────────────

def scrape_civicengage(name, jobs_url, base_url):
    jobs = []
    try:
        r    = requests.get(jobs_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=re.compile(r"UniqueId|JobID", re.I)):
            title = a.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            href     = a["href"]
            full_url = href if href.startswith("http") else base_url.rstrip("/") + href
            parent   = a.find_parent(["li", "div", "tr", "article"])
            date_m   = re.search(r"\d{1,2}/\d{1,2}/\d{4}", parent.get_text() if parent else "")
            posted   = date_m.group(0) if date_m else ""
            cat, reason = categorize(title)
            if cat:
                jobs.append(make_job(name, title, full_url, "CivicPlus",
                                      category=cat, location=name, posted=posted, match_reason=reason))
        log.info(f"{name}: {len(jobs)} jobs")
    except Exception as e:
        log.error(f"{name}: {e}")
    return jobs


def scrape_bella_vista():
    name = "City of Bella Vista"
    url  = "https://recruiting.paylocity.com/recruiting/jobs/All/b1e8c19e-977f-41ec-89e7-a138ab6e72eb/City-of-Bella-Vista"
    jobs = []
    soup = pw_get_soup(url, wait=4)
    if not soup:
        return jobs
    added = set()
    for a in soup.find_all("a", href=True):
        href  = a["href"]
        title = a.get_text(strip=True)
        if not title or len(title) < 5 or href in added:
            continue
        if not any(x in href for x in ["recruiting/jobs", "Details", "b1e8c19e"]):
            continue
        added.add(href)
        full_url = href if href.startswith("http") else "https://recruiting.paylocity.com" + href
        cat, reason = categorize(title)
        if cat:
            jobs.append(make_job(name, title, full_url, "Paylocity",
                                  category=cat, location="Bella Vista, AR", match_reason=reason))
    log.info(f"{name}: {len(jobs)} jobs")
    return jobs


def scrape_lowell():
    name = "Lowell (City)"
    url  = "https://www.lowellarkansas.gov/jobs"
    jobs = []
    try:
        r    = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        jobs = scrape_links(soup, name, url, "HTML", location="Lowell, AR")
        log.info(f"{name}: {len(jobs)} jobs")
    except Exception as e:
        log.error(f"{name}: {e}")
    return jobs


def scrape_washington_county():
    name = "Washington County AR"
    url  = "https://www.washingtoncountyar.gov/government/departments-f-z/human-resources/job-postings"
    jobs = []
    try:
        r    = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        jobs = scrape_links(soup, name, url, "HTML", location="Washington County, AR")
        log.info(f"{name}: {len(jobs)} jobs")
    except Exception as e:
        log.error(f"{name}: {e}")
    return jobs


def scrape_ar_state_jobs():
    name = "AR State Jobs (NWA)"
    url  = "https://arcareers.arkansas.gov/search/?searchby=location&q=&locationsearch=northwest+arkansas"
    jobs = []
    soup = pw_get_soup(url, wait=5)
    if not soup:
        return jobs
    added = set()
    for a in soup.find_all("a", href=re.compile(r"/job/|/go/|requisition", re.I)):
        title    = a.get_text(strip=True)
        href     = a["href"]
        if not title or len(title) < 5 or href in added:
            continue
        added.add(href)
        full_url = href if href.startswith("http") else "https://arcareers.arkansas.gov" + href
        cat, reason = categorize(title)
        if cat:
            jobs.append(make_job(name, title, full_url, "SuccessFactors",
                                  category=cat, location="NW Arkansas", match_reason=reason))
    log.info(f"{name}: {len(jobs)} jobs")
    return jobs


def scrape_adp():
    name = "ADP (NWA)"
    url  = "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?cid=a75698d1-4927-42e2-8b24-4b1e4d60fa54&ccId=19000101_000001&lang=en_US"
    jobs = []
    soup = pw_get_soup(url, wait=5)
    if not soup:
        return jobs
    added = set()
    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        href  = a["href"]
        if not title or len(title) < 5 or href in added:
            continue
        if not any(x in href for x in ["recruitment", "job", "posting", "req"]):
            continue
        added.add(href)
        full_url = href if href.startswith("http") else "https://workforcenow.adp.com" + href
        cat, reason = categorize(title)
        if cat:
            jobs.append(make_job(name, title, full_url, "ADP",
                                  category=cat, match_reason=reason))
    log.info(f"{name}: {len(jobs)} jobs")
    return jobs


# ──────────────────────────────────────────────────────────────────────────────
# LIBRARY / ARTS / UNIVERSITY SCRAPERS
# ──────────────────────────────────────────────────────────────────────────────

def scrape_springdale_library():
    name = "Springdale Public Library"
    url  = "https://springdalelibrary.org/employment/"
    jobs = []
    try:
        r       = requests.get(url, headers=HEADERS, timeout=15)
        soup    = BeautifulSoup(r.text, "html.parser")
        content = soup.find("main") or soup.find(class_=re.compile(r"content|entry|post", re.I)) or soup
        if any(x in content.get_text().lower() for x in ["no open position", "no current"]):
            log.info(f"{name}: no open positions")
            return jobs
        for a in content.find_all("a", href=True):
            title = a.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            href = a["href"]
            if any(x in href for x in ["#", "mailto", "tel:", "/wp-"]):
                continue
            cat, reason = categorize(title)
            if cat:
                full_url = href if href.startswith("http") else "https://springdalelibrary.org" + href
                jobs.append(make_job(name, title, full_url, "Library",
                                      category=cat, location="Springdale, AR", match_reason=reason))
        log.info(f"{name}: {len(jobs)} jobs")
    except Exception as e:
        log.error(f"{name}: {e}")
    return jobs


def scrape_faylib():
    name = "Fayetteville Public Library"
    url  = "https://www.faylib.org/work-8103"
    jobs = []
    try:
        r       = requests.get(url, headers=HEADERS, timeout=15)
        soup    = BeautifulSoup(r.text, "html.parser")
        content = soup.find("main") or soup.find(class_=re.compile(r"content|entry|post", re.I)) or soup
        if any(x in content.get_text().lower() for x in ["no open position", "no current openings"]):
            log.info(f"{name}: no open positions")
            return jobs
        for a in content.find_all("a", href=True):
            title = a.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            href = a["href"]
            if any(x in href for x in ["#", "mailto", "tel:", "facebook", "twitter", "instagram"]):
                continue
            cat, reason = categorize(title)
            if cat:
                full_url = href if href.startswith("http") else "https://www.faylib.org" + href
                jobs.append(make_job(name, title, full_url, "HTML",
                                      category=cat, location="Fayetteville, AR", match_reason=reason))
        log.info(f"{name}: {len(jobs)} jobs")
    except Exception as e:
        log.error(f"{name}: {e}")
    return jobs


def scrape_walton_arts():
    name = "Walton Arts Center"
    url  = "https://waltonartscenter.org/about/employment/"
    jobs = []
    try:
        r       = requests.get(url, headers=HEADERS, timeout=15)
        soup    = BeautifulSoup(r.text, "html.parser")
        content = soup.find("main") or soup.find(class_=re.compile(r"content|entry|post", re.I)) or soup
        skip    = ["#", "mailto", "tel:", "facebook", "twitter", "instagram", "linkedin"]
        for a in content.find_all("a", href=True):
            title = a.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            href = a["href"]
            if any(x in href for x in skip):
                continue
            if "/about/employment/" not in href and href.startswith("/"):
                continue
            cat, reason = categorize(title)
            if cat:
                full_url = href if href.startswith("http") else "https://waltonartscenter.org" + href
                jobs.append(make_job(name, title, full_url, "HTML",
                                      category=cat, location="Fayetteville, AR", match_reason=reason))
        log.info(f"{name}: {len(jobs)} jobs")
    except Exception as e:
        log.error(f"{name}: {e}")
    return jobs


def scrape_workday(source):
    name     = source["name"]
    api_url  = source["api_url"]
    location_hint = source.get("location", "")
    jobs     = []
    offset   = 0
    limit    = 20
    api_hdrs = {**HEADERS, "Content-Type": "application/json", "Accept": "application/json"}

    while True:
        payload = {"limit": limit, "offset": offset, "searchText": "", "appliedFacets": {}}
        try:
            r        = requests.post(api_url, json=payload, headers=api_hdrs, timeout=20)
            data     = r.json()
            postings = data.get("jobPostings", [])
            total    = data.get("total", 0)
            if offset == 0:
                log.info(f"{name}: {total} total from Workday API")
            for p in postings:
                title    = p.get("title", "").strip()
                ext_url  = p.get("externalPath", "")
                full_url = source["base_url"].rstrip("/") + ext_url if ext_url else source["base_url"]
                posted   = p.get("postedOn", "")
                loc      = p.get("locationsText", "") or p.get("primaryLocation", "") or location_hint
                cat, reason = categorize(title)
                if cat:
                    jobs.append(make_job(name, title, full_url, "Workday",
                                          category=cat, location=loc, posted=posted, match_reason=reason))
            offset += limit
            if not postings or offset >= total:
                break
            time.sleep(0.4)
        except Exception as e:
            log.error(f"{name} Workday: {e}")
            break

    log.info(f"{name}: {len(jobs)} relevant jobs")
    return jobs


def scrape_jbu(url, name):
    jobs = []
    try:
        r       = requests.get(url, headers=HEADERS, timeout=15)
        soup    = BeautifulSoup(r.text, "html.parser")
        content = soup.find("main") or soup.find(id=re.compile(r"content|main", re.I)) or soup
        skip    = ["#", "mailto", "facebook", "twitter", "linkedin", "instagram",
                   "jbu.edu/about", "jbu.edu/admissions", "jbu.edu/student",
                   "jbu.edu/academic", "eaglenet", "catalog", "calendar", "news", "giving", "alumni"]
        for a in content.find_all("a", href=True):
            title = a.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            href = a["href"]
            if any(x in href for x in skip):
                continue
            cat, reason = categorize(title)
            if cat:
                full_url = href if href.startswith("http") else "https://www.jbu.edu" + href
                jobs.append(make_job(name, title, full_url, "HubSpot",
                                      category=cat, location="Siloam Springs, AR", match_reason=reason))
        log.info(f"{name}: {len(jobs)} jobs")
    except Exception as e:
        log.error(f"{name}: {e}")
    return jobs


def scrape_careersnwa(url, name, location=""):
    """Scraper for a single talent.careersnwa.com company page — server-rendered,
    plain requests work. `name` is the known employer for this page."""
    jobs = []
    try:
        r    = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        added = set()
        for a in soup.find_all("a", href=True):
            href  = a["href"]
            title = a.get_text(strip=True)
            if not title or len(title) < 5 or href in added:
                continue
            if "/jobs/" not in href:
                continue
            added.add(href)
            full_url = href if href.startswith("http") else "https://talent.careersnwa.com" + href
            cat, reason = categorize(title)
            if cat:
                jobs.append(make_job(name, title, full_url, "CareersNWA",
                                      category=cat, location=location, match_reason=reason))
    except Exception as e:
        log.error(f"{name} (CareersNWA): {e}")
    log.info(f"{name}: {len(jobs)} jobs")
    return jobs


_SLUG_HEX_RE = re.compile(r"^[0-9a-f]{6,}$", re.I)
_SLUG_UUID_TAIL_RE = re.compile(
    r"-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_SLUG_SMALL_WORDS = {"of", "and", "the", "in", "on", "for", "at"}
_SLUG_NAME_OVERRIDES = {
    "uaf": "University of Arkansas",
    "nwacc": "NWACC",
    "jbu": "JBU",
    "jb-hunt": "J.B. Hunt",
    "arcbest": "ArcBest",
}


def _company_name_from_slug(slug):
    """talent.careersnwa.com company slugs look like 'tyson-foods' or
    'sps-commerce-2-30a3f118-afb2-...' (a trailing dedup UUID). Turn either
    into a readable employer name so it can be shown as the actual company
    instead of a generic 'CareersNWA' tag."""
    if slug in _SLUG_NAME_OVERRIDES:
        return _SLUG_NAME_OVERRIDES[slug]
    slug = _SLUG_UUID_TAIL_RE.sub("", slug)
    parts = [p for p in slug.split("-") if p]
    while parts and _SLUG_HEX_RE.match(parts[-1]):
        parts.pop()
    if not parts:
        return slug
    return " ".join(p if p.lower() in _SLUG_SMALL_WORDS else p.capitalize() for p in parts)


def scrape_careersnwa_regional():
    """The platform-wide Marketing & Communications feed spans every employer
    on CareersNWA, not just the ones hardcoded in CAREERSNWA_SOURCES — so each
    job's real employer is parsed from its /companies/<slug>/jobs/... URL
    rather than tagged with the feed's own name."""
    label = "CareersNWA regional feed"
    jobs = []
    try:
        r    = requests.get(CAREERSNWA_REGIONAL_FEED, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        added = set()
        for a in soup.find_all("a", href=True):
            href  = a["href"]
            title = a.get_text(strip=True)
            if not title or len(title) < 5 or href in added:
                continue
            m = re.search(r"/companies/([^/]+)/jobs/", href)
            if not m:
                continue
            added.add(href)
            company  = _company_name_from_slug(m.group(1))
            full_url = href if href.startswith("http") else "https://talent.careersnwa.com" + href
            cat, reason = categorize(title)
            if cat:
                jobs.append(make_job(company, title, full_url, "CareersNWA",
                                      category=cat, match_reason=reason))
    except Exception as e:
        log.error(f"{label}: {e}")
    log.info(f"{label}: {len(jobs)} jobs")
    return jobs


# ──────────────────────────────────────────────────────────────────────────────
# ADZUNA (optional — only runs if ADZUNA_APP_ID / ADZUNA_APP_KEY are set)
# ──────────────────────────────────────────────────────────────────────────────

def scrape_adzuna():
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        log.info("Adzuna: ADZUNA_APP_ID/ADZUNA_APP_KEY not set — skipping")
        return []

    SEARCHES = [
        "outreach librarian", "communications librarian", "marketing librarian",
        "library assistant", "librarian", "communications coordinator",
        "marketing coordinator", "public relations coordinator",
        "community engagement coordinator", "events coordinator",
    ]
    jobs, seen = [], set()
    for query in SEARCHES:
        try:
            params = {
                "app_id":           ADZUNA_APP_ID,
                "app_key":          ADZUNA_APP_KEY,
                "results_per_page": 10,
                "what_phrase":      query,
                "where":            "Fayetteville AR",
                "distance":         30,
                "sort_by":          "date",
            }
            r = requests.get("https://api.adzuna.com/v1/api/jobs/us/search/1",
                              params=params, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                log.warning(f"Adzuna [{query}]: HTTP {r.status_code}")
                time.sleep(1)
                continue
            for job in r.json().get("results", []):
                title    = (job.get("title") or "").strip()
                job_url  = job.get("redirect_url") or ""
                company  = (job.get("company") or {}).get("display_name", "")
                loc_text = (job.get("location") or {}).get("display_name", "")
                if not title or not job_url or not is_valid_location(loc_text):
                    continue
                dk = (title.lower().strip(), company.lower().strip())
                if dk in seen:
                    continue
                seen.add(dk)
                cat, reason = categorize(title)
                if not cat:
                    continue
                src = f"Adzuna · {company}" if company else "Adzuna"
                job_rec = make_job(src, title, job_url, "Adzuna",
                                    category=cat, location=loc_text, match_reason=reason)
                job_rec["id"] = make_id(src, title)  # Adzuna redirect URLs change per call
                jobs.append(job_rec)
            time.sleep(1)
        except Exception as e:
            log.error(f"Adzuna [{query}]: {e}")
    log.info(f"Adzuna: {len(jobs)} jobs")
    return jobs


# ──────────────────────────────────────────────────────────────────────────────
# ORCHESTRATION
# ──────────────────────────────────────────────────────────────────────────────

def scrape_all():
    all_jobs = []

    log.info("── School districts ──")
    for d in APPLITRACK_DISTRICTS:
        all_jobs.extend(_safe(scrape_applitrack, d, label=d["name"]))
    for d in TEDK12_DISTRICTS:
        all_jobs.extend(_safe(scrape_tedk12, d, label=d["name"]))
    all_jobs.extend(_safe(scrape_smartrecruiters))
    all_jobs.extend(_safe(scrape_springdale_sd))
    all_jobs.extend(_safe(scrape_westfork))
    all_jobs.extend(_safe(scrape_haashall))
    for d in SCHOOLSPRING_DISTRICTS:
        all_jobs.extend(_safe(scrape_schoolspring, d, label=d["name"], pause=2))

    log.info("── Government / county ──")
    all_jobs.extend(_safe(scrape_civicengage, "Rogers (City)",
                           "https://www.rogersar.gov/Jobs.aspx", "https://www.rogersar.gov",
                           label="Rogers (City)"))
    all_jobs.extend(_safe(scrape_bella_vista, pause=2))
    all_jobs.extend(_safe(scrape_lowell))
    all_jobs.extend(_safe(scrape_washington_county))
    all_jobs.extend(_safe(scrape_ar_state_jobs, pause=2))
    all_jobs.extend(_safe(scrape_adp, pause=2))

    log.info("── Libraries / universities / arts ──")
    all_jobs.extend(_safe(scrape_springdale_library))
    all_jobs.extend(_safe(scrape_faylib))
    all_jobs.extend(_safe(scrape_walton_arts))
    for s in WORKDAY_SOURCES:
        all_jobs.extend(_safe(scrape_workday, s, label=s["name"]))
    all_jobs.extend(_safe(scrape_jbu, "https://www.jbu.edu/human-resources/staff-job-listings/", "JBU (Staff)", label="JBU (Staff)"))
    all_jobs.extend(_safe(scrape_jbu, "https://www.jbu.edu/human-resources/faculty-job-listings/", "JBU (Faculty)", label="JBU (Faculty)"))

    log.info("── CareersNWA (regional platform) ──")
    for s in CAREERSNWA_SOURCES:
        all_jobs.extend(_safe(scrape_careersnwa, s["url"], s["name"], s.get("location", ""),
                               label=s["name"], pause=1))
    all_jobs.extend(_safe(scrape_careersnwa_regional, label="CareersNWA regional feed", pause=1))

    log.info("── Aggregators ──")
    all_jobs.extend(_safe(scrape_adzuna, pause=2))

    # Deduplicate by ID, drop remote postings that slipped past the title-based
    # "remote" exclude (e.g. remote noted only in the location field), and drop
    # any library/hybrid match from a K-12 school district — Arkansas requires
    # a teaching license for those regardless of how the title is worded (a
    # bare "Librarian" posting from a district wouldn't be caught by the
    # "school librarian"/"library media specialist" keyword excludes above).
    seen, unique = set(), []
    for j in all_jobs:
        if j["id"] in seen:
            continue
        if "remote" in (j.get("location", "") or "").lower():
            continue
        if SOURCE_TYPE_BY_NAME.get(j["district"]) == "school" and j["category"] in ("library", "hybrid"):
            continue
        seen.add(j["id"])
        unique.append(j)

    by_source = {}
    for j in unique:
        by_source[j["district"]] = by_source.get(j["district"], 0) + 1
    log.info("── Per-source summary ──")
    for src in sorted(by_source):
        log.info(f"  {src}: {by_source[src]}")
    log.info(f"Total relevant jobs: {len(unique)}")
    return unique


def find_new_jobs(old_data, new_jobs):
    existing_ids = {j["id"] for j in old_data.get("jobs", [])}
    return [j for j in new_jobs if j["id"] not in existing_ids]


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    log.info("── NWA Marketing + Library Job Tracker starting ──")
    old_data  = load_jobs()
    new_jobs  = scrape_all()
    existing  = {j["id"]: j for j in old_data.get("jobs", [])}
    for j in new_jobs:
        if j["id"] in existing:
            j["first_seen"] = existing[j["id"]]["first_seen"]
    brand_new = find_new_jobs(old_data, new_jobs)
    log.info(f"New since last run: {len(brand_new)}")
    save_jobs({
        "last_updated": datetime.now().isoformat(timespec="minutes"),
        "jobs":    new_jobs,
        "sources": ALL_SOURCES,
    })
    log.info("── Done ──")


if __name__ == "__main__":
    main()
