# If I Were a PhD Student — Honest Critical Review
### SafeTravel LK Research Project — IT22629180

---

> **Preface:** This is an honest critique, not praise. The goal is to help you answer the panel confidently by knowing your project's real strengths AND its real weaknesses before they point them out.

---

## The Biggest Problem First

**Your project has no primary data.**

Everything you collected — Reddit, TripAdvisor, YouTube, TikTok, Google News — is secondary data. Someone else observed something, wrote it down somewhere on the internet, and you collected it. 

In a PhD thesis, this is a serious methodological vulnerability. A panel examiner will immediately ask: *"How do you know any of this reflects reality in Sri Lanka today?"*

A PhD student would start with **one primary source** — even a small one — and use the automated pipeline as supplementary scale. Your project does it backwards.

I will come back to what I would add. First, let me go through each source.

---

## SOURCES I WOULD KEEP (and why)

### ✅ Sri Lanka Certified News Sites (Ada Derana, Newsfirst, Daily Mirror, etc.)
**Keep. Strongest collected sources you have.**

Why: Editorial oversight, legal accountability, .lk registered domains, Press Council membership. These are the closest thing to verified sources your automated system can collect. The weighting system you built is correct here.

**What I would do differently:** I would contact these newsrooms directly and ask for their archived tourism-incident articles. A formal data request letter — even if declined — shows academic rigor.

---

### ✅ Google News RSS
**Keep.**

Why: Google Publisher Policies enforce editorial standards. Only registered news publishers are indexed. This is editorially filtered journalism, not random UGC.

**What I would do differently:** Log the publisher name for each article (e.g., BBC, Reuters, Daily Mirror). Right now the source is just tagged `google_news` — you can't distinguish a BBC article from a local blog that Google happened to index.

---

### ✅ WikiVoyage
**Keep. One of your most defensible sources.**

Why: CC BY-SA 3.0 licence makes it formally citable. Wikimedia Foundation standards apply. You can literally put the URL and licence in your bibliography.

---

### ✅ TripAdvisor Reviews.csv (with credibility weighting)
**Keep — but reclassify what it is.**

Why: 16,156 structured entries with Helpful_Votes and User_Contributions give you real credibility signals. The weighting system is correct. 

**What I would do differently:** I would apply for TripAdvisor's official academic data access programme instead of using a scraped CSV. That turns "data I found somewhere" into "data TripAdvisor officially provided for my research."

---

### ✅ Google Maps Reviews
**Keep — but reduce reliance.**

Why: Location-linked reviews are more credible than context-free posts. The geographic anchor is real validation.

---

## SOURCES I WOULD REMOVE ENTIRELY

### ❌ TikTok
**Remove completely from the core methodology.**

Why:
1. **Platform design is against you.** TikTok is optimised for engagement and entertainment. Creators have strong financial incentives to exaggerate, dramatise, and sensationalise. A video titled "I WAS SCAMMED IN SRI LANKA 😱" gets more views than an accurate, nuanced account.
2. **Terms of Service violation.** TikTok's ToS explicitly prohibits automated scraping. Using Apify to collect TikTok data for academic research creates legal and ethical exposure.
3. **No credibility signal.** View count on TikTok correlates with entertainment value, not factual accuracy.
4. **Caption quality.** TikTok captions are almost always too short to pass meaningful NLP analysis.
5. **Demographic bias.** TikTok skews heavily young. It does not represent the full tourist demographic (families, older travellers).

**Verdict:** The signal-to-noise ratio is so low that removing TikTok would likely *improve* your model accuracy. I would remove it and note this in the paper as a deliberate methodological choice.

---

### ❌ Instagram
**Remove completely.**

Why:
1. **Same ToS problem as TikTok.** Instagram prohibits automated scraping. Apify-based collection is a terms violation.
2. **Captions are decorative, not factual.** Instagram is a visual platform. Captions are typically 1-3 sentences, emoji-heavy, and context-free.
3. **Brand-sponsored content.** Many travel Instagram posts are paid promotions. A "negative" caption may be performing relatability, not reporting a genuine incident.
4. **Lowest weight in the system (0.27) already tells you something.** If you assigned it 0.27 yourself, you already know you don't trust it. If you don't trust it, why include it?

**Verdict:** Remove. Acknowledge in the paper that Instagram was evaluated and excluded due to insufficient textual signal and ToS compliance concerns.

---

### ❌ Facebook Groups (via Apify)
**Remove or fundamentally change approach.**

Why:
1. **ToS violation.** Facebook explicitly prohibits scraping in its terms. Using Apify to collect Facebook group data — even from public groups — is a terms violation that would concern any ethics review board.
2. **"Public" does not mean "consented to research."** People posting in a Facebook group about Sri Lanka travel expect their posts to be read by group members, not harvested into an academic database. This is an ethics concern.
3. **No credibility signals.** Facebook has no meaningful upvote system, no editorial oversight, and accounts are trivially created.
4. **If a university ethics committee reviewed this data collection, they would flag it.**

**What I would do differently:** If you want community data, use Reddit (which has a formal research programme) instead of Facebook (which does not).

---

### ❌ Twitter/X via Nitter Mirror
**Remove.**

Why:
1. **Nitter is legally grey.** Nitter is a third-party scraper of Twitter content. Twitter has repeatedly tried to shut it down. Using Nitter data in academic research creates provenance problems — the data source is an unofficial mirror of a commercial platform that explicitly prohibits scraping.
2. **Twitter/X has degenerated significantly in data quality.** Since 2022, Twitter/X has reduced content quality and increased noise.
3. **Twitter has an Academic Research API.** If you want Twitter data, the correct approach is to apply for the Twitter/X Academic Research track (now called X API v2 Academic Research). Using a scraper mirror instead signals you bypassed the official process.

**What I would do differently:** Either formally apply for Twitter Academic API access, or exclude Twitter entirely. The Nitter mirror approach is the worst option academically.

---

### ⚠️ YouTube Transcripts — Keep but Reduce Scope
**Keep for verified channels only. Question the rest.**

Why to reduce:
1. YouTube video transcripts are often auto-generated captions — they contain errors, miss tone, and cannot capture visual context.
2. Collecting transcripts from 30+ queries generates huge volume with unknown quality.
3. Small YouTube channels (under 10K subscribers) have essentially no credibility signal.

**What I would do differently:**
- Only collect from channels with ≥50,000 subscribers (verified signal)
- Manually review a sample of 20 videos to check if NLP classification is accurate
- Acknowledge auto-caption error rates as a limitation

---

### ⚠️ Reddit — Keep but Fix the Compliance Issue
**Keep the methodology. Fix the ethics problem.**

The Reddit for Researchers (RFR) programme exists specifically for academic use. The current system collects data under standard developer access — which Reddit's policy says is not authorised for academic research.

**What I would do differently:**
- Apply for RFR programme access formally
- If RFR is denied, limit Reddit usage to demonstrating the system architecture and exclude it from core results
- Clearly disclose in the paper which API tier was used

---

## WHAT I WOULD ADD (Things Completely Missing From Your Project)

### 1. 🎯 Primary Data — Tourist Survey at Colombo Airport
**This is the biggest gap. A PhD project without primary data is a system demo, not a study.**

What: A structured questionnaire administered to departing tourists at Bandaranaike International Airport or major tourist hotels (Colombo, Kandy, Galle). Ask:
- Did you experience a scam or safety incident during your visit?
- What type? (list the 14 categories)
- Which location?
- Did you report it to anyone?

Even 50-100 completed surveys would give you **primary, first-hand verified data** to compare against the system's predictions. This is called **ground-truth validation** — your NLP pipeline says Colombo Fort is high-risk for tuk-tuk scams; your survey says 40% of tourists there experienced tuk-tuk overcharging. That's a validated finding.

**Why this changes everything:** You can write: *"The system's risk predictions were validated against primary survey data collected from N=87 departing tourists at BIA."* That is a PhD-level claim. What you currently have is not.

---

### 2. 🏛️ Formal SLTDA Data Request
**Write a formal letter to the Sri Lanka Tourism Development Authority.**

SLTDA is the government body responsible for tourism regulation in Sri Lanka. They may have:
- Tourist complaint records
- Incident statistics by region
- Registered/licensed guide lists (useful for fake guide validation)

Even if they decline, the letter and their response is evidence of rigorous methodology. If they provide even aggregated statistics, it becomes a primary government source — the most credible data possible.

Contact: info@sltda.gov.lk | www.sltda.gov.lk

---

### 3. 👮 Tourist Police Data Request
**Contact Sri Lanka Tourist Police (Hotline: 1912).**

The Tourist Police maintain records of reported incidents. A formal data request for anonymized, aggregated incident statistics by location and type would provide ground-truth government data that no scraping system can match.

This also directly connects your research to the panel's comment about "sharing alerts with authorities" — if Tourist Police are aware of your research, you have a real stakeholder relationship.

---

### 4. 📋 Formal Ethics Approval
**This should have been done before data collection started.**

Any research involving data collection about people's experiences requires ethics committee review. Most universities have an Institutional Review Board (IRB) or Research Ethics Committee (REC).

The questions an ethics committee would ask:
- Are people's personal posts being collected without their knowledge?
- Is the data stored securely?
- Could the research cause harm?
- Is data anonymized?

At minimum, your paper's methodology section should state: *"This research was conducted in accordance with [University] Research Ethics Guidelines. Data collection was limited to publicly available content. No personally identifiable information was collected or stored."* If your university requires formal approval for web scraping research, you need that approval document.

---

### 5. 📝 Manual Ground-Truth Annotation (Inter-Rater Reliability)
**How do you know your NLP is correct?**

A PhD standard for validating a classifier:
1. Take a random sample of 300 records from your database
2. Have 2-3 human annotators (yourself + 2 others) label each one: Is this a scam? What type? What risk level?
3. Measure agreement between annotators using **Cohen's Kappa** (κ)
4. Compare their labels to the NLP pipeline's labels
5. Report precision, recall, F1-score per scam category

This is called **inter-rater reliability** and it's a standard measure of data quality in NLP research. Without it, you cannot claim your classifier is accurate — you can only claim it runs.

---

### 6. 🌍 Language Coverage Acknowledgment
**The biggest silent bias in your entire system.**

Your system only collects and processes English-language content. But major tourist groups visiting Sri Lanka include:
- Chinese tourists (the largest single nationality visiting Sri Lanka)
- German, French, Russian, Japanese tourists
- Indian tourists (who often write in Hindi or Malayalam)

**This means your system has a massive English-language sampling bias.** Chinese tourists who experience scams and post about it in Mandarin on Weibo or WeChat are completely invisible to your system.

In a PhD thesis, this must be explicitly stated as a limitation. In a better-resourced project, you would add multilingual NLP (at minimum Chinese, German, French).

---

### 7. 🔬 Comparison Baseline (Ablation Study)
**How do you know your system is better than nothing?**

A PhD study would include a **baseline comparison**:
- Baseline A: Simple keyword search (no NLP, no ML)
- Baseline B: Keyword + sentiment only (no scam taxonomy)  
- Your system: Full NLP + ML + weighting

Then show that your system catches more true scam reports and fewer false positives than the baselines. This is called an **ablation study** and it demonstrates that your complexity is justified.

---

## WHAT I WOULD DO DIFFERENTLY — SUMMARY

| Current Approach | PhD Approach |
|---|---|
| 11 sources including TikTok, Instagram, Nitter | 6–7 sources, all legally compliant, higher quality |
| All secondary (scraped) data | Primary survey data + secondary automated data |
| No ethics approval mentioned | Formal ethics committee approval before collection |
| NLP accuracy not externally validated | Ground-truth annotation + inter-rater reliability (Cohen's Kappa) |
| No SLTDA/Tourist Police contact | Formal data request letters sent and documented |
| English-only collection | English collection + explicit multilingual limitation disclosure |
| Apify-dependent sources (ToS issues) | Only official APIs or ToS-compliant scraping |
| Reddit via standard dev API | Reddit via RFR program OR excluded from core results |
| No comparison to baseline | Ablation study comparing NLP tiers |
| Risk score not validated against reality | Validated against primary tourist survey responses |

---

## WHAT YOUR PROJECT DOES WELL (Be Proud of These)

1. **The 4-gate strict filter** — Genuinely good engineering. Most studies that use social media data don't filter this rigorously.

2. **The source credibility weighting system** — Now that you've implemented it, this is an academically defensible contribution. Most similar projects treat all sources equally.

3. **The scam taxonomy (14 categories)** — Comprehensive and specific to Sri Lanka. This is a real research contribution.

4. **The multi-source corroboration approach** — The idea that a risk score requires agreement across multiple independent sources is methodologically sound.

5. **The NLP pipeline (3-tier: keyword → TF-IDF+RF → DistilBERT)** — The graceful fallback architecture is well-designed.

6. **Personalized safety tips by traveller profile** — This is practically useful and shows the research has a clear real-world application.

---

## The One Sentence Summary

> *If I were a PhD student, I would do fewer sources but better — remove TikTok, Instagram, Facebook, and Nitter entirely; add one primary data source (even 50 tourist surveys); get formal ethics approval; manually annotate 200 records for ground-truth validation; and contact SLTDA and Tourist Police in writing. The automated pipeline is impressive, but without primary data and ethics approval, it is an engineering project, not a research study.*

---

## What To Do Before Your Panel/Viva

**Immediately (today):**
- [ ] Email SLTDA: info@sltda.gov.lk — introduce your research, ask if any tourism incident statistics are available
- [ ] Add a clear limitations section to your paper covering: English-only bias, no primary data, Reddit compliance, no ethics approval
- [ ] Frame TikTok/Instagram/Facebook as "evaluated and excluded from core results" rather than "primary sources"

**For the panel:**
- Be the first one to mention the limitations — examiners respect researchers who know their own weaknesses
- Say: *"The biggest limitation of this work is the absence of primary data. Future work would include a tourist survey at Colombo airport to ground-truth validate the system's predictions."*

---

*Written as an honest peer review — SafeTravel LK, IT22629180*
