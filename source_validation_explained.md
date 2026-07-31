# How Each Source Is Validated & How Data Enters the System
### SafeTravel LK — Plain Language Explanation (IT22629180)

---

## The Big Idea First (Read This Before Anything Else)

**"Validation" in this research does NOT mean proving that each post is 100% true.**

In research, validation means:
> *"Applying systematic quality checks so that only relevant, credible, and consistent signals influence the result — and being transparent about what those checks are."*

Think of it like a doctor diagnosing a disease. They don't need every test to be perfect. They collect many signals (blood test, X-ray, symptoms, patient history), weigh each one by reliability, and make a conclusion. No single signal alone is enough — but together they form an evidence base.

That is exactly what this system does.

---

## Overall Data Flow — How ANYTHING Gets Into the Database

Every single piece of data — from Reddit, YouTube, TripAdvisor, or anywhere — must pass through the **same four automatic gates** before it is stored:

```
RAW DATA ARRIVES (text from any source)
        │
        ▼
┌────────────────────────────────────────────────┐
│  GATE 1: Geographic Check                      │
│  Does the text mention Sri Lanka, Colombo,     │
│  Kandy, Galle, Ella, Sigiriya, etc.?           │
│  NO → REJECTED immediately                     │
└────────────────────────────────────────────────┘
        │ Passes ▼
┌────────────────────────────────────────────────┐
│  GATE 2: Tourism Context Check                 │
│  Is the person a tourist/traveller?            │
│  Must contain words like: tourist, traveler,   │
│  backpacker, vacation, hostel, tuk-tuk, etc.   │
│  NO → REJECTED                                 │
└────────────────────────────────────────────────┘
        │ Passes ▼
┌────────────────────────────────────────────────┐
│  GATE 3: Negative Experience Check             │
│  Does it describe something bad?               │
│  Must contain: scam, ripped off, harassed,     │
│  stolen, dangerous, unsafe, warning, etc.      │
│  NO → REJECTED                                 │
└────────────────────────────────────────────────┘
        │ Passes ▼
┌────────────────────────────────────────────────┐
│  GATE 4: Hard Exclusion Check                  │
│  Is it actually about foreign criminals,       │
│  politics, election, cricket, crypto, etc.?    │
│  YES → REJECTED (30+ exclusion patterns)       │
└────────────────────────────────────────────────┘
        │ Passes ALL 4 Gates ▼
┌────────────────────────────────────────────────┐
│  NLP ANALYSIS                                  │
│  • What type of scam?                          │
│  • How negative is the sentiment? (-1 to +1)   │
│  • Risk level? (1=Low, 2=Medium, 3=High)       │
│  • Which specific location in Sri Lanka?        │
└────────────────────────────────────────────────┘
        │
        ▼
┌────────────────────────────────────────────────┐
│  LOCATION REQUIREMENT                          │
│  Must have a specific named place              │
│  (not just "Sri Lanka" in general)             │
│  NO LOCATION → REJECTED                        │
└────────────────────────────────────────────────┘
        │
        ▼
  STORED IN DATABASE ✅
```

**This process runs the same way for every source, no exceptions.**

---

## Source-by-Source Breakdown

---

### SOURCE 1: Reddit

#### What it is
A forum website where real travellers share experiences. The system searches 25+ subreddits (communities) like r/srilanka, r/travel, r/solotravel using 40+ search keyword combinations.

#### How the data gets in
```
Reddit website
     │
     │ Python code makes HTTP requests to Reddit's public JSON API
     │ (no login needed — Reddit posts are publicly visible)
     ▼
Raw posts collected (title + post text + comment count + upvotes)
     │
     │ First filter inside the collector:
     │   - Skip posts with score < 1 AND 0 comments (nobody engaged = noise)
     │   - Skip deleted/removed posts
     ▼
Passes through the 4 Gates above
     ▼
NLP Analysis → Stored in DB (if it has a specific location)
```

#### What CAN be validated about Reddit
| Signal | What It Tells Us |
|---|---|
| **Reddit upvotes (score)** | Other community members agreed it was worth reading |
| **Number of comments** | People engaged with it — it sparked discussion |
| **Multiple posts saying same thing** | Not one person's unique complaint — a pattern |
| **Which subreddit** | r/Scams is dedicated to scam reports; r/solotravel has experienced travellers |

#### What CANNOT be validated
- Whether the specific event the person describes actually happened
- Whether the person is who they say they are
- The exact date, place, or amount of money involved

#### What to write in the paper
> *"Reddit posts were collected via the public Reddit JSON API across 25+ relevant subreddits. Posts with zero engagement (score < 1, no comments) were excluded. Reddit data functions as a high-volume, real-time signal source. Individual posts are unverifiable; only aggregate patterns across multiple independent posts are used to influence risk scores. Reddit data is classified as Tier 3 (unverified UGC) in our source hierarchy."*

---

### SOURCE 2: TripAdvisor (Reviews.csv)

#### What it is
A structured dataset of 16,156 tourist reviews from TripAdvisor, covering 20 cities across Sri Lanka. Each row has a rating (1–5 stars), review text, the reviewer's home country, their total contribution count, how many people found the review helpful, and when they travelled.

#### How the data gets in
```
Reviews.csv file (already stored locally in E:\research\)
     │
     │ import_reviews_csv.py reads the file
     │ ReviewAnalyzer processes it (ratings, sentiment, patterns)
     ▼
Each row checked for negative content (Rating ≤ 2 OR scam keywords in text)
     │
     │ Positive reviews (4–5 stars with no negative keywords) are used
     │ only for training the ML model (baseline comparison), not as alerts
     ▼
Negative reviews → NLP Analysis → Stored in DB
```

#### The built-in credibility signals in the CSV
| CSV Field | How It Helps Validate |
|---|---|
| `Helpful_Votes` | How many OTHER people said "yes, this was useful" — if 20 people clicked helpful, 20 independent travellers agreed the review was worth reading |
| `User_Contributions` | A reviewer with 500 total reviews is an established user — harder to fake. A reviewer with 1 total review is suspicious |
| `Rating` | 1-star rating is a strong signal — combined with negative text, it is consistently negative |
| `Travel_Date` | Multiple reviews from different years saying the same thing = persistent problem, not a one-off |
| `User_Location` | Reviewers from different countries (Australia, Germany, USA) complaining about the same location independently is a strong pattern signal |

#### What CANNOT be validated
- Whether the individual review is completely accurate
- Whether the reviewer fabricated the experience

#### Validation approach for the paper
Apply **Credibility Weighting**:
- `Helpful_Votes ≥ 5` → weight ×1.5 (peer-validated by other travellers)
- `User_Contributions ≥ 100` → weight ×1.3 (established reviewer)
- `Rating = 1` AND scam keywords → highest negative signal

#### What to write in the paper
> *"The TripAdvisor Reviews.csv dataset (16,156 entries) contains anonymised user IDs, ratings, travel dates, and review text. Credibility weighting is applied using Helpful_Votes (peer validation by independent travellers) and User_Contributions (reviewer experience level). This dataset is classified as Tier 2 (semi-verified) when reviews carry Helpful_Votes ≥ 5, and Tier 3 otherwise."*

---

### SOURCE 3: YouTube

#### What it is
The system searches YouTube for videos about Sri Lanka tourist scams using 30+ keyword queries. It then downloads the **video transcript** (the auto-generated captions / subtitles) and treats the spoken words as text.

#### How the data gets in
```
YouTube Data API (Google's official API, requires API key)
     │
     │ Searches for videos matching queries like:
     │ "Sri Lanka tourist scam 2024", "tuk tuk scam Colombo", etc.
     ▼
Video transcript (captions) extracted
     │
     │ Transcript text treated as review text
     ▼
Same 4 Gates → NLP Analysis → DB
```

#### What CAN be validated about YouTube
| Signal | What It Tells Us |
|---|---|
| **View count** | A video with 500,000 views that says "I was scammed at Kandy temple" reached a huge audience — the platform itself validated its reach |
| **Comments** | Viewers often comment "same thing happened to me!" — independent corroboration |
| **Channel credibility** | Established travel channels (100K+ subscribers) have reputation to protect — less likely to fabricate |
| **Video URL is permanent** | The source is traceable and auditable |

#### What CANNOT be validated
- Whether the creator's story is 100% accurate
- Whether they dramatized events for views (clickbait concern)

#### What to write in the paper
> *"YouTube video transcripts were collected via the YouTube Data API v3 using 30+ search queries. Transcripts provide spoken-word accounts from travellers documenting safety incidents. YouTube is classified as Tier 3 (user-generated), with view count and channel subscriber count serving as proxy credibility indicators."*

---

### SOURCE 4: Google News RSS

#### What it is
Google News aggregates articles from real news organisations. The system reads the RSS feed (a list of headlines and article summaries) for Sri Lanka travel safety topics.

#### How the data gets in
```
Google News RSS feed (public, no API key needed)
     │
     │ social.py collector reads the XML feed
     │ Extracts headline + article summary for each news item
     ▼
Same 4 Gates → NLP → DB
```

#### Why this is more reliable than Reddit
Google News **only includes articles from recognised news publishers** — not random blog posts. Articles have:
- A journalist's name (accountability)
- An editor (editorial oversight)
- A publication that can be sued for defamation (legal accountability)

#### What to write in the paper
> *"Google News RSS feeds were used to collect journalism-sourced content about tourist safety incidents in Sri Lanka. News articles are classified as Tier 2 (semi-verified) due to editorial oversight and journalistic standards, while acknowledging that sensationalism and inaccuracies can exist in published media."*

---

### SOURCE 5: Sri Lanka News Sites (10+ outlets)

#### What it is
Local Sri Lankan news websites including Daily Mirror, Newsfirst, The Island, Ada Derana, etc. These report on incidents happening inside Sri Lanka.

#### Why this matters
If a major scam operation is exposed or a tourist is assaulted, the local Sri Lankan press will report it. This is domestic journalism with knowledge of local context.

#### What to write in the paper
> *"Content from 10+ Sri Lankan news outlets was collected to capture domestically-reported tourist safety incidents. Local journalism provides contextual accuracy regarding Sri Lankan geography, law enforcement, and cultural practices that international sources may lack."*

---

### SOURCE 6: WikiVoyage

#### What it is
A free, open-content travel guide published under the **Creative Commons Attribution-ShareAlike 3.0 licence (CC BY-SA 3.0)** — the same licence as Wikipedia. It is managed by the Wikimedia Foundation.

#### Why this is the most citable non-government source
- **Formally licensed** — CC BY-SA 3.0 means it can legally be cited in research
- **Community-edited** — multiple contributors review each other's additions
- **Safety sections are factual summaries** — not personal stories
- **URL is stable and permanent** — can be cited with access date

The WikiVoyage Sri Lanka Safety section explicitly describes tuk-tuk scams, gem shop scams, and beach harassment — making it a citable, open-licence source that confirms the system's scam categories.

#### What to write in the paper
> *"WikiVoyage safety content (CC BY-SA 3.0) was collected as an open-licence, community-curated reference source. WikiVoyage is classified as Tier 1.5 — between official government sources and semi-verified platforms — due to its formal open licence and Wikimedia Foundation editorial standards."*

---

### SOURCE 7: Google Maps Reviews

#### What it is
Reviews left by visitors on Google Maps for specific tourist locations in Sri Lanka. Collected via Apify (a web automation platform).

#### Why location-linked reviews are more credible
Google Maps reviews are **linked to a real physical place**. If someone reviews "Sigiriya Rock Fortress" negatively and says "the unofficial guide demanded money", they must have been AT Sigiriya to leave that review (Google verifies location in many cases via GPS).

#### What to write in the paper
> *"Google Maps reviews were collected via Apify for major tourist attractions. Location-linked reviews are classified as Tier 2 due to their geographic verification mechanism and the fact that reviewers must physically visit or have knowledge of a specific place to submit a review."*

---

### SOURCE 8: Facebook Groups

#### What it is
Public Facebook travel groups where tourists share experiences. Collected via Apify.

#### Validation limitation
Facebook group posts are the **least verifiable** of all sources — anonymous accounts, no upvote system, no credibility signals. The system uses them for volume/trend detection only.

#### What to write in the paper
> *"Facebook public travel group data was collected as supplementary volume data. Due to limited credibility signals, Facebook posts are treated as Tier 3 (lowest trust) and only contribute to scam type frequency counts, not to individual risk level calculations."*

---

### SOURCE 9: TikTok / Instagram

#### What it is
Social media posts and captions about Sri Lanka travel safety. Collected via Apify using hashtag searches.

#### Validation approach
Same as Facebook — purely supplementary. The NLP still applies all 4 gates. A single TikTok post about a gem scam does nothing on its own. But if 50 TikTok posts from different creators all describe the same gem shop scam in Colombo, that pattern matters.

---

## The Most Important Validation: Cross-Source Corroboration

**This is the key concept to explain to the panel.**

No single source validates anything. But when **three independent sources from different platforms describe the same scam at the same location**, the system's NLP tags it consistently — and the risk score increases.

**Example — Tuk-Tuk Scam at Colombo Fort:**

| Source | What it says |
|---|---|
| Reddit (r/travel) | "Tuk-tuk driver took me to gem shops, wouldn't go where I asked" |
| TripAdvisor Review (Helpful_Votes: 12) | "Driver demanded double the agreed price at Colombo Fort" |
| Google News (Daily Mirror) | "Tourist Police issue warning about tuk-tuk overcharging at Fort" |
| **UK FCDO (GOV.UK)** ✅ | *"Agree a price before you set off or look for one with a working meter"* |

Three unverified sources all saying the same thing → Pattern detected.
One government document confirming the pattern exists → **Pattern validated.**

---

## The Government Documents — Your Verified Anchors

These are REAL, FREE, OFFICIAL government documents you can cite directly. They confirm the same risks your system detects:

| Document | URL | What It Confirms |
|---|---|---|
| **UK FCDO Travel Advice — Sri Lanka** | gov.uk/foreign-travel-advice/sri-lanka/safety-and-security | Bag snatching, tuk-tuk overcharging, harassment of women, pickpocketing on trains, drink spiking, dangerous roads |
| **US State Department — Sri Lanka** | travel.state.gov → Sri Lanka | Level 1 advisory, crime warnings |
| **Australia DFAT — Sri Lanka** | smartraveller.gov.au/destinations/asia/sri-lanka | Petty crime, scams, road safety |
| **WikiVoyage Sri Lanka** | wikivoyage.org/wiki/Sri_Lanka | CC BY-SA 3.0 licensed scam descriptions |

**How to use these in your paper:**

Create a table in the Data Validation section like this:

| Scam Type Detected by System | Confirmed by UK FCDO? | Confirmed by US State Dept? |
|---|---|---|
| Tuk-Tuk Scam | ✅ Yes — explicitly stated | ✅ Yes |
| Theft / Robbery | ✅ Yes — bag snatching, pickpocketing | ✅ Yes |
| Harassment | ✅ Yes — "verbal and physical harassment" | ✅ Yes |
| Accident / Hazard | ✅ Yes — "erratic driving, frequent accidents" | ✅ Yes |
| Physical Assault | ✅ Yes — "spiked drinks, assault" | ✅ Yes |

This table **is your validation evidence for the panel.**

---

## Summary Table — One Line Per Source

| Source | How Data Gets In | Validated By | Trust Level |
|---|---|---|---|
| **UK FCDO / US State Dept** | Manual citation in paper | Government authority | ✅ Highest |
| **WikiVoyage** | HTTP scrape | CC BY-SA 3.0 open licence | ✅ High |
| **Google News RSS** | RSS feed reader | Editorial journalism standards | 🟡 Medium-High |
| **Sri Lanka News Sites** | HTTP scraper | Domestic published media | 🟡 Medium |
| **Google Maps Reviews** | Apify scraper | Location-linked, peer-marked | 🟡 Medium |
| **TripAdvisor CSV** | CSV file + import script | Helpful_Votes + contributor score | 🟡 Medium (weighted) |
| **YouTube** | YouTube Data API v3 | View count + channel size | 🟠 Medium-Low |
| **Reddit** | Public JSON API | Upvote score + comment count | 🟠 Low-Medium |
| **TikTok / Instagram / Facebook** | Apify scraper | Volume/pattern only | 🔴 Low |

**All sources pass the same 4-gate filter before storage.**
**Low-trust sources only matter when they corroborate high-trust sources.**
**Government documents are the final validation anchor for all scam categories.**

---

*Plain language explanation prepared for panel response — SafeTravel LK, IT22629180*
