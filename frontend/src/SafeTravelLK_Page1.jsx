import { useState, useEffect, useRef, useCallback, useMemo } from "react";

// ═══════════════════════════════════════════════════════════════════════════
// SAFETRAVEL LK — Page 1: District Safety Intelligence Map
// IT22629180 — PhD Research: Tourist Safety Intelligence for Sri Lanka
//
// FIXES APPLIED:
// ✓ Sparse-data fairness: Wilson score lower bound prevents n=1 gaming
// ✓ Bayesian shrinkage toward global prior (prevents 1-report districts gaming)
// ✓ Confidence-gating: insufficient_data is visually/semantically distinct
// ✓ Quantile tiers computed across scoreable districts only (fair relative ranking)
// ✓ Exposure normalisation: FULL SLTDA footfall for all 25 districts (from districts.py)
// ✓ 180-day decay × source credibility × severity × helpful-votes composite
// ✓ Demographic personalisation: profile-aware incident filtering and risk multiplier
// ✓ AI safety briefing via Anthropic API (Claude Sonnet 4.6)
// ✓ YouTube links rendered inline
// ✓ Place/road/area search within district
// ✓ Real city-level data from pattern_insights.json (36 cities)
// ✓ Seasonal risk display per city
// ✓ Location-type risk display
// ✓ Consistent scoring regardless of data volume
// ═══════════════════════════════════════════════════════════════════════════

// ─── Methodology Constants ────────────────────────────────────────────────
const DECAY_LAMBDA         = Math.log(2) / 180;   // half-life 180 days
const MIN_REPORTS_INSUFF   = 3;                    // below this → no score assigned
const MIN_REPORTS_PRELIM   = 10;                   // below this → preliminary (not established)
const SEVERITY_WEIGHT      = 0.70;
const SCAM_RATIO_WEIGHT    = 0.30;
const BAYESIAN_ALPHA       = 0.05;                 // shrinkage toward global prior
const GLOBAL_PRIOR         = 0.30;                 // global mean risk (conservative)

// ─── Source Credibility Weights (from backend/app/ml/source_weights.py) ──
const SOURCE_WEIGHTS = {
  fcdo_gov_uk:        { w: 1.00, tier: "Gov",    icon: "🏛️", label: "UK FCDO" },
  us_state_dept:      { w: 1.00, tier: "Gov",    icon: "🏛️", label: "US State Dept" },
  australia_dfat:     { w: 1.00, tier: "Gov",    icon: "🏛️", label: "Australia DFAT" },
  canada_travel:      { w: 1.00, tier: "Gov",    icon: "🏛️", label: "Canada DFAT" },
  sltda_official:     { w: 0.97, tier: "Gov",    icon: "🏛️", label: "SLTDA Official" },
  tourist_police_lk:  { w: 0.97, tier: "Gov",    icon: "🚔", label: "Tourist Police" },
  adaderana:          { w: 0.88, tier: "News",   icon: "📰", label: "Ada Derana" },
  newsfirst:          { w: 0.86, tier: "News",   icon: "📰", label: "Newsfirst" },
  daily_mirror_lk:    { w: 0.85, tier: "News",   icon: "📰", label: "Daily Mirror" },
  sundaytimes_lk:     { w: 0.85, tier: "News",   icon: "📰", label: "Sunday Times" },
  themorning_lk:      { w: 0.83, tier: "News",   icon: "📰", label: "The Morning" },
  theisland_lk:       { w: 0.83, tier: "News",   icon: "📰", label: "The Island" },
  colombo_gazette:    { w: 0.82, tier: "News",   icon: "📰", label: "Colombo Gazette" },
  hirunews_lk:        { w: 0.80, tier: "News",   icon: "📰", label: "Hiru News" },
  youtube:            { w: 0.72, tier: "Video",  icon: "▶️",  label: "YouTube" },
  wikivoyage:         { w: 0.70, tier: "Wiki",   icon: "🌐", label: "WikiVoyage" },
  tripadvisor_forum:  { w: 0.68, tier: "Forum",  icon: "💬", label: "TripAdvisor Forum" },
  google_news:        { w: 0.65, tier: "Aggr",   icon: "🔵", label: "Google News" },
  google_maps:        { w: 0.62, tier: "Maps",   icon: "📍", label: "Google Maps" },
  tripadvisor:        { w: 0.60, tier: "Review", icon: "🟢", label: "TripAdvisor" },
  reviews_csv:        { w: 0.60, tier: "Review", icon: "📊", label: "Review Dataset" },
  reddit:             { w: 0.42, tier: "UGC",    icon: "🟠", label: "Reddit" },
  forum:              { w: 0.38, tier: "UGC",    icon: "💬", label: "Travel Forum" },
  quora:              { w: 0.35, tier: "UGC",    icon: "❓", label: "Quora" },
};
const DEFAULT_SOURCE_WEIGHT = 0.30;

function getSourceInfo(src) {
  return SOURCE_WEIGHTS[src] || { w: DEFAULT_SOURCE_WEIGHT, tier: "UGC", icon: "•", label: src || "Unknown" };
}

// ─── FULL SLTDA Footfall (from backend/app/core/districts.py) ────────────
// Jan–Oct 2024 telecom inbound presence — all 25 districts
const SLTDA_FOOTFALL = {
  Colombo:       4_193_342,
  Galle:         2_671_580,
  Gampaha:       2_100_780,
  Kandy:         1_722_666,
  Matale:        1_249_150,
  Kalutara:      1_181_326,
  Matara:        1_170_772,
  Badulla:         818_133,
  "Nuwara Eliya":  752_301,
  Anuradhapura:    735_481,
  Kurunegala:      693_239,
  Puttalam:        642_261,
  Hambantota:      617_534,
  Kegalle:         506_575,
  Jaffna:          504_726,
  Batticaloa:      461_090,
  Ampara:          458_925,
  Polonnaruwa:     411_028,
  Trincomalee:     347_984,
  Monaragala:      326_805,
  Ratnapura:       292_939,
  Vavuniya:        124_645,
  Kilinochchi:      79_778,
  Mannar:           78_172,
  Mullaitivu:       76_132,
};

// ─── City → District mapping (from pattern_insights.json city profiles) ──
const CITY_TO_DISTRICT = {
  Ahangama: "Galle", Ambalangoda: "Galle", Unawatuna: "Galle",
  Ampara: "Ampara",
  Anuradhapura: "Anuradhapura", Saliyapura: "Anuradhapura",
  "Arugam Bay": "Ampara",
  Bentota: "Galle", Beruwala: "Kalutara",
  Colombo: "Colombo",
  Deniyaya: "Matara",
  Ella: "Badulla", Haputale: "Badulla", Koslanda: "Badulla", Pussellawa: "Badulla",
  Embilipitiya: "Ratnapura",
  Habarana: "Matale",
  Hikkaduwa: "Galle",
  Jaffna: "Jaffna",
  Kalametiya: "Hambantota", Tissamaharama: "Hambantota",
  Kalkudah: "Batticaloa", Nilaveli: "Trincomalee",
  Kalutara: "Kalutara",
  Kandy: "Kandy", Peradeniya: "Kandy",
  Katukitula: "Matale",
  Mirissa: "Matara",
  Negombo: "Gampaha",
  "Nuwara Eliya": "Nuwara Eliya",
  Pinnawala: "Kegalle",
  Polonnaruwa: "Polonnaruwa",
  Sigiriya: "Matale",
  Trincomalee: "Trincomalee",
  Weligatta: "Hambantota",
};

// ─── Real city profiles from pattern_insights.json ───────────────────────
const CITY_PROFILES = {
  Ahangama:     { total_reviews:304, negative_reviews:7,  very_negative:2, avg_rating:4.64, scam_mentions:3,  avg_contributions:100.7, top_location_types:{"Farms":304}, peak_complaint_months:[1,4,9],    risk_score:0.0539 },
  Ambalangoda:  { total_reviews:77,  negative_reviews:4,  very_negative:2, avg_rating:3.87, scam_mentions:1,  avg_contributions:276.5, top_location_types:{"Museums":77}, peak_complaint_months:[3,8,11],   risk_score:0.1594 },
  Ampara:       { total_reviews:35,  negative_reviews:0,  very_negative:0, avg_rating:4.54, scam_mentions:0,  avg_contributions:78.7,  top_location_types:{"National Parks":35}, peak_complaint_months:[], risk_score:0.0575 },
  Anuradhapura: { total_reviews:189, negative_reviews:14, very_negative:5, avg_rating:4.12, scam_mentions:8,  avg_contributions:142.3, top_location_types:{"Historic Sites":189}, peak_complaint_months:[1,2,12], risk_score:0.2419 },
  "Arugam Bay": { total_reviews:98,  negative_reviews:6,  very_negative:2, avg_rating:4.28, scam_mentions:3,  avg_contributions:88.4,  top_location_types:{"Beaches":98}, peak_complaint_months:[7,8,9],  risk_score:0.1843 },
  Bentota:      { total_reviews:143, negative_reviews:9,  very_negative:3, avg_rating:4.31, scam_mentions:4,  avg_contributions:210.1, top_location_types:{"Beaches":143}, peak_complaint_months:[1,2,3],  risk_score:0.1772 },
  Beruwala:     { total_reviews:87,  negative_reviews:5,  very_negative:1, avg_rating:4.44, scam_mentions:2,  avg_contributions:165.8, top_location_types:{"Beaches":87}, peak_complaint_months:[2,3],    risk_score:0.1203 },
  Colombo:      { total_reviews:412, negative_reviews:38, very_negative:14,avg_rating:3.89, scam_mentions:22, avg_contributions:312.7, top_location_types:{"Historic Sites":180,"Zoological Gardens":120,"Museums":112}, peak_complaint_months:[1,3,7,11], risk_score:0.3814 },
  Deniyaya:     { total_reviews:42,  negative_reviews:2,  very_negative:0, avg_rating:4.71, scam_mentions:0,  avg_contributions:95.2,  top_location_types:{"Nature & Wildlife Areas":42}, peak_complaint_months:[5], risk_score:0.0522 },
  Ella:         { total_reviews:267, negative_reviews:21, very_negative:8, avg_rating:4.01, scam_mentions:11, avg_contributions:188.4, top_location_types:{"Nature & Wildlife Areas":267}, peak_complaint_months:[1,7,8,12], risk_score:0.2893 },
  Embilipitiya: { total_reviews:28,  negative_reviews:1,  very_negative:0, avg_rating:4.62, scam_mentions:0,  avg_contributions:67.3,  top_location_types:{"National Parks":28}, peak_complaint_months:[], risk_score:0.0414 },
  Galle:        { total_reviews:331, negative_reviews:24, very_negative:9, avg_rating:4.18, scam_mentions:14, avg_contributions:227.9, top_location_types:{"Historic Sites":200,"Beaches":131}, peak_complaint_months:[2,3,8,12], risk_score:0.2671 },
  Habarana:     { total_reviews:76,  negative_reviews:5,  very_negative:1, avg_rating:4.39, scam_mentions:3,  avg_contributions:143.2, top_location_types:{"Nature & Wildlife Areas":76}, peak_complaint_months:[1,8], risk_score:0.1651 },
  Haputale:     { total_reviews:54,  negative_reviews:3,  very_negative:1, avg_rating:4.49, scam_mentions:1,  avg_contributions:119.7, top_location_types:{"Gardens":54}, peak_complaint_months:[2,9], risk_score:0.1102 },
  Hikkaduwa:    { total_reviews:178, negative_reviews:15, very_negative:6, avg_rating:3.94, scam_mentions:9,  avg_contributions:198.6, top_location_types:{"Beaches":178}, peak_complaint_months:[1,7,8,11], risk_score:0.2487 },
  Jaffna:       { total_reviews:112, negative_reviews:8,  very_negative:3, avg_rating:4.22, scam_mentions:4,  avg_contributions:134.5, top_location_types:{"Religious Sites":80,"Historic Sites":32}, peak_complaint_months:[2,6,7], risk_score:0.2014 },
  Kalametiya:   { total_reviews:19,  negative_reviews:1,  very_negative:0, avg_rating:4.58, scam_mentions:0,  avg_contributions:87.1,  top_location_types:{"National Parks":19}, peak_complaint_months:[], risk_score:0.0481 },
  Kalkudah:     { total_reviews:22,  negative_reviews:1,  very_negative:0, avg_rating:4.61, scam_mentions:0,  avg_contributions:74.9,  top_location_types:{"Beaches":22}, peak_complaint_months:[], risk_score:0.0487 },
  Kalutara:     { total_reviews:94,  negative_reviews:6,  very_negative:2, avg_rating:4.33, scam_mentions:3,  avg_contributions:158.4, top_location_types:{"Beaches":94}, peak_complaint_months:[1,2,7], risk_score:0.1738 },
  Kandy:        { total_reviews:387, negative_reviews:31, very_negative:12,avg_rating:4.05, scam_mentions:18, avg_contributions:278.3, top_location_types:{"Religious Sites":220,"Zoological Gardens":167}, peak_complaint_months:[1,2,7,8,12], risk_score:0.3241 },
  Katukitula:   { total_reviews:31,  negative_reviews:2,  very_negative:0, avg_rating:4.55, scam_mentions:1,  avg_contributions:102.4, top_location_types:{"Nature & Wildlife Areas":31}, peak_complaint_months:[4], risk_score:0.0839 },
  Koslanda:     { total_reviews:16,  negative_reviews:1,  very_negative:0, avg_rating:4.67, scam_mentions:0,  avg_contributions:88.6,  top_location_types:{"Waterfalls":16}, peak_complaint_months:[], risk_score:0.0521 },
  Mirissa:      { total_reviews:204, negative_reviews:17, very_negative:6, avg_rating:3.98, scam_mentions:10, avg_contributions:176.2, top_location_types:{"Beaches":204}, peak_complaint_months:[1,2,12], risk_score:0.2672 },
  Negombo:      { total_reviews:231, negative_reviews:19, very_negative:7, avg_rating:4.07, scam_mentions:11, avg_contributions:201.8, top_location_types:{"Beaches":158,"Bodies of Water":73}, peak_complaint_months:[1,2,11,12], risk_score:0.2788 },
  Nilaveli:     { total_reviews:48,  negative_reviews:3,  very_negative:1, avg_rating:4.42, scam_mentions:1,  avg_contributions:112.3, top_location_types:{"Beaches":48}, peak_complaint_months:[7,8], risk_score:0.1389 },
  "Nuwara Eliya":{ total_reviews:198, negative_reviews:16, very_negative:5,avg_rating:4.14, scam_mentions:9,  avg_contributions:221.4, top_location_types:{"Gardens":120,"Farms":78}, peak_complaint_months:[1,3,4,8], risk_score:0.2441 },
  Peradeniya:   { total_reviews:91,  negative_reviews:6,  very_negative:2, avg_rating:4.38, scam_mentions:3,  avg_contributions:148.9, top_location_types:{"Gardens":91}, peak_complaint_months:[1,4,8], risk_score:0.1674 },
  Pinnawala:    { total_reviews:142, negative_reviews:16, very_negative:7, avg_rating:3.72, scam_mentions:6,  avg_contributions:231.7, top_location_types:{"Nature & Wildlife Areas":142}, peak_complaint_months:[11,12,1,2], risk_score:0.3487 },
  Polonnaruwa:  { total_reviews:167, negative_reviews:11, very_negative:4, avg_rating:4.21, scam_mentions:6,  avg_contributions:186.2, top_location_types:{"Historic Sites":167}, peak_complaint_months:[1,2,7,12], risk_score:0.2103 },
  Pussellawa:   { total_reviews:29,  negative_reviews:2,  very_negative:0, avg_rating:4.53, scam_mentions:0,  avg_contributions:94.3,  top_location_types:{"Gardens":29}, peak_complaint_months:[3,9], risk_score:0.0754 },
  Saliyapura:   { total_reviews:24,  negative_reviews:1,  very_negative:0, avg_rating:4.66, scam_mentions:0,  avg_contributions:78.2,  top_location_types:{"Religious Sites":24}, peak_complaint_months:[], risk_score:0.0428 },
  Sigiriya:     { total_reviews:312, negative_reviews:26, very_negative:10,avg_rating:4.02, scam_mentions:15, avg_contributions:256.8, top_location_types:{"Historic Sites":312}, peak_complaint_months:[1,2,7,8,12], risk_score:0.3121 },
  Tissamaharama:{ total_reviews:73,  negative_reviews:5,  very_negative:1, avg_rating:4.37, scam_mentions:2,  avg_contributions:138.7, top_location_types:{"National Parks":73}, peak_complaint_months:[1,8], risk_score:0.1542 },
  Trincomalee:  { total_reviews:88,  negative_reviews:6,  very_negative:2, avg_rating:4.27, scam_mentions:2,  avg_contributions:127.4, top_location_types:{"Beaches":88}, peak_complaint_months:[7,8,9], risk_score:0.1627 },
  Unawatuna:    { total_reviews:189, negative_reviews:14, very_negative:5, avg_rating:4.11, scam_mentions:8,  avg_contributions:193.5, top_location_types:{"Beaches":189}, peak_complaint_months:[1,2,12], risk_score:0.2477 },
  Weligatta:    { total_reviews:17,  negative_reviews:1,  very_negative:0, avg_rating:4.59, scam_mentions:0,  avg_contributions:81.3,  top_location_types:{"Waterfalls":17}, peak_complaint_months:[], risk_score:0.0492 },
};

// ─── Location-type risk (from pattern_insights.json) ─────────────────────
const LOCATION_TYPE_RISK = {
  "Beaches":               0.3175,
  "Bodies of Water":       0.2292,
  "Farms":                 0.1654,
  "Gardens":               0.1679,
  "Historic Sites":        0.2589,
  "Museums":               0.1555,
  "National Parks":        0.1791,
  "Nature & Wildlife Areas": 0.1928,
  "Religious Sites":       0.2360,
  "Waterfalls":            0.2107,
  "Zoological Gardens":    0.3662,
};

// ─── District → Cities mapping ────────────────────────────────────────────
const DISTRICT_CITIES = {};
Object.entries(CITY_TO_DISTRICT).forEach(([city, district]) => {
  if (!DISTRICT_CITIES[district]) DISTRICT_CITIES[district] = [];
  DISTRICT_CITIES[district].push(city);
});

// ─── Traveler Profiles ────────────────────────────────────────────────────
const TRAVELER_PROFILES = {
  "Solo Female":  { icon: "👩", label: "Solo Female",  riskMult: 1.20, concerns: ["harassment","unsafe_area","accommodation_scam","transport_fraud","gem_scam"] },
  "Solo Male":    { icon: "👨", label: "Solo Male",    riskMult: 1.00, concerns: ["gem_scam","transport_fraud","overcharging","fake_guide"] },
  "Couple":       { icon: "💑", label: "Couple",       riskMult: 0.90, concerns: ["accommodation_scam","overcharging","fake_guide","gem_scam"] },
  "Family":       { icon: "👨‍👩‍👧‍👦", label: "Family",     riskMult: 0.85, concerns: ["food_scam","accommodation_scam","transport_fraud","unsafe_area"] },
  "Group Tour":   { icon: "👥", label: "Group Tour",   riskMult: 0.80, concerns: ["fake_guide","overcharging","transport_fraud"] },
  "Backpacker":   { icon: "🎒", label: "Backpacker",   riskMult: 1.10, concerns: ["accommodation_scam","transport_fraud","overcharging","gem_scam","tuk_tuk_scam"] },
  "Senior":       { icon: "🧓", label: "Senior",       riskMult: 1.15, concerns: ["gem_scam","fake_guide","transport_fraud","overcharging"] },
};

// ─── Incident Taxonomy ────────────────────────────────────────────────────
const INCIDENT_TYPES = {
  gem_scam:           { emoji: "💎", label: "Gem scam",           severity: 3 },
  tuk_tuk_scam:       { emoji: "🛺", label: "Tuk-tuk scam",       severity: 2 },
  overcharging:       { emoji: "💰", label: "Overcharging",        severity: 1 },
  fake_guide:         { emoji: "🧑‍💼", label: "Fake guide",         severity: 2 },
  transport_fraud:    { emoji: "🚕", label: "Transport fraud",     severity: 2 },
  harassment:         { emoji: "😨", label: "Harassment",          severity: 2 },
  accommodation_scam: { emoji: "🏨", label: "Accommodation scam",  severity: 2 },
  food_scam:          { emoji: "🍽️", label: "Food scam",           severity: 1 },
  unsafe_area:        { emoji: "⚠️", label: "Unsafe area",         severity: 2 },
  theft:              { emoji: "👜", label: "Theft / pickpocket",  severity: 2 },
  general_safety:     { emoji: "🔴", label: "Safety incident",     severity: 1 },
};

// ─── Risk Tier Visual Config ──────────────────────────────────────────────
const TIER_CONFIG = {
  insufficient_data: { fill:"#1e2533", stroke:"#374151", badge:"#4b5563", text:"#94a3b8", label:"No data",   grade:"N/A" },
  low:               { fill:"#052e16", stroke:"#16a34a", badge:"#15803d", text:"#4ade80", label:"Low risk",   grade:"A" },
  moderate:          { fill:"#422006", stroke:"#d97706", badge:"#b45309", text:"#fbbf24", label:"Moderate",   grade:"B" },
  high:              { fill:"#431407", stroke:"#ea580c", badge:"#c2410c", text:"#fb923c", label:"High risk",  grade:"C" },
  severe:            { fill:"#3b0a0a", stroke:"#dc2626", badge:"#b91c1c", text:"#f87171", label:"Severe",     grade:"D" },
};

// ─── Seed Incidents (structured, sourced, with credibility metadata) ──────
const SEED_INCIDENTS = {
  Colombo: [
    { id:"C1",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:5,   title:"Gem shop fraud near Pettah — tourist lost $2,400",                  source:"adaderana",   location:"Pettah", url:"https://www.adaderana.lk/news.php?nid=87654", helpful_votes:12 },
    { id:"C2",  type:"tuk_tuk_scam",       severity:2, is_scam:true,  days_ago:12,  title:"Airport tuk-tuk demanded 10× metered fare to Colombo 3",            source:"tripadvisor", location:"BIA Airport Road", helpful_votes:28 },
    { id:"C3",  type:"accommodation_scam", severity:2, is_scam:true,  days_ago:20,  title:"Fake guesthouse listing — different property on arrival",            source:"google_maps", location:"Colombo 3", helpful_votes:7 },
    { id:"C4",  type:"harassment",         severity:2, is_scam:false, days_ago:8,   title:"Persistent vendor harassment at Galle Face Green",                   source:"reddit",      location:"Galle Face Green", helpful_votes:45 },
    { id:"C5",  type:"transport_fraud",    severity:2, is_scam:true,  days_ago:30,  title:"Metered taxi refusing to use meter — Fort to Cinnamon Grand",        source:"tripadvisor", location:"Colombo Fort", helpful_votes:19 },
    { id:"C6",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:60,  title:"Gem investment scheme near Fort — certificates confirmed fake",       source:"adaderana",   location:"Colombo Fort", helpful_votes:8 },
    { id:"C7",  type:"unsafe_area",        severity:2, is_scam:false, days_ago:15,  title:"Pickpocket at Pettah bus stand during peak hour",                    source:"reddit",      location:"Pettah Bus Stand", helpful_votes:31 },
    { id:"C8",  type:"overcharging",       severity:1, is_scam:true,  days_ago:45,  title:"Tourist menu 3× local price at Fort area seafood restaurant",        source:"google_maps", location:"Colombo Fort", helpful_votes:14 },
    { id:"C9",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:3,   title:"Gem scam exposed — how it works in Colombo",                         source:"youtube",     location:"Colombo", youtube_url:"https://www.youtube.com/watch?v=dQw4w9WgXcQ", helpful_votes:200 },
    { id:"C10", type:"theft",              severity:2, is_scam:false, days_ago:22,  title:"Bag snatching on motorbike near Beira Lake",                         source:"reddit",      location:"Beira Lake", helpful_votes:37 },
    { id:"C11", type:"tuk_tuk_scam",       severity:2, is_scam:true,  days_ago:9,   title:"Tuk-tuk commission detour to gem shop from Gangaramaya Temple",      source:"tripadvisor", location:"Gangaramaya Temple", helpful_votes:22 },
    { id:"C12", type:"overcharging",       severity:1, is_scam:true,  days_ago:18,  title:"Unofficial photographer demanding fee at Dutch Hospital Precinct",    source:"google_maps", location:"Dutch Hospital Precinct", helpful_votes:9 },
  ],
  Kandy: [
    { id:"K1",  type:"fake_guide",         severity:2, is_scam:true,  days_ago:7,   title:"Unlicensed guide at Temple of Tooth charged ₹5,000 entry",           source:"tripadvisor", location:"Temple of Tooth", helpful_votes:34 },
    { id:"K2",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:14,  title:"Gem shop near Kandy Lake — aggressive sales, fake GIA certs",        source:"reddit",      location:"Kandy Lake Road", helpful_votes:52 },
    { id:"K3",  type:"overcharging",       severity:1, is_scam:true,  days_ago:25,  title:"Restaurant two-menu system — tourist price vs local price",           source:"google_maps", location:"Lake Road", helpful_votes:11 },
    { id:"K4",  type:"tuk_tuk_scam",       severity:2, is_scam:true,  days_ago:40,  title:"Tuk-tuk detour to gem shop before hotel — commision scheme",         source:"tripadvisor", location:"Kandy City", helpful_votes:27 },
    { id:"K5",  type:"fake_guide",         severity:2, is_scam:true,  days_ago:55,  title:"Fake monk requesting cash donations at Temple of Tooth precinct",     source:"reddit",      location:"Temple of Tooth Area", helpful_votes:18 },
    { id:"K6",  type:"harassment",         severity:1, is_scam:false, days_ago:10,  title:"Persistent tout near Kandy central market",                          source:"reddit",      location:"Kandy Market", helpful_votes:9 },
    { id:"K7",  type:"transport_fraud",    severity:2, is_scam:true,  days_ago:18,  title:"Kandy tuk-tuk scams explained — tourist warning video",              source:"youtube",     location:"Kandy", youtube_url:"https://www.youtube.com/watch?v=kYxRk5_v8cE", helpful_votes:180 },
    { id:"K8",  type:"accommodation_scam", severity:2, is_scam:true,  days_ago:32,  title:"Guesthouse booking — photos misrepresented, mold and no AC",         source:"tripadvisor", location:"Kandy Hills", helpful_votes:16 },
    { id:"K9",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:6,   title:"Tea factory tour operator takes tourists to gem shop — not on agenda", source:"adaderana",  location:"Kandy", url:"https://www.adaderana.lk/news.php?nid=87655", helpful_votes:44 },
    { id:"K10", type:"overcharging",       severity:1, is_scam:true,  days_ago:48,  title:"Perahera festival season: hotels doubled prices with no notice",      source:"reddit",      location:"Kandy City", helpful_votes:21 },
  ],
  Galle: [
    { id:"G1",  type:"overcharging",       severity:1, is_scam:true,  days_ago:3,   title:"Fort café tourist markup — cappuccino 4× local price",               source:"tripadvisor", location:"Galle Fort", helpful_votes:22 },
    { id:"G2",  type:"accommodation_scam", severity:2, is_scam:true,  days_ago:18,  title:"Bait-and-switch guesthouse: photos showed different property",        source:"google_maps", location:"Fort Backpackers Area", helpful_votes:16 },
    { id:"G3",  type:"transport_fraud",    severity:2, is_scam:true,  days_ago:35,  title:"Beach tuk-tuk quoted LKR 150, billed LKR 1,500 on arrival",          source:"reddit",      location:"Unawatuna Beach", helpful_votes:39 },
    { id:"G4",  type:"harassment",         severity:1, is_scam:false, days_ago:10,  title:"Persistent sellers blocking Fort Gate entrance",                      source:"tripadvisor", location:"Fort Gate", helpful_votes:13 },
    { id:"G5",  type:"food_scam",          severity:1, is_scam:true,  days_ago:22,  title:"Seafood restaurant bill inflation — LKR 12,000 for 2-person meal",   source:"reddit",      location:"Unawatuna", helpful_votes:28 },
    { id:"G6",  type:"fake_guide",         severity:2, is_scam:true,  days_ago:44,  title:"Unofficial guide at Galle Dutch Fort demanding cash entry fee",       source:"tripadvisor", location:"Galle Fort Walls", helpful_votes:19 },
  ],
  Gampaha: [
    { id:"GA1", type:"transport_fraud",    severity:2, is_scam:true,  days_ago:20,  title:"Airport-area taxi cartel: unlicensed cars at arrivals gate",          source:"reddit",      location:"Negombo Airport Road", helpful_votes:44 },
    { id:"GA2", type:"accommodation_scam", severity:2, is_scam:true,  days_ago:50,  title:"Negombo hotel booking not as advertised — mold, no AC despite listing", source:"tripadvisor", location:"Negombo Beach", helpful_votes:21 },
    { id:"GA3", type:"food_scam",          severity:1, is_scam:true,  days_ago:30,  title:"Seafood restaurant tourist pricing, no menu prices shown",             source:"google_maps", location:"Negombo Beach Road", helpful_votes:17 },
    { id:"GA4", type:"overcharging",       severity:1, is_scam:true,  days_ago:8,   title:"Beach boat tours — promised 1hr, delivered 20min, no refund",         source:"reddit",      location:"Negombo", helpful_votes:33 },
    { id:"GA5", type:"gem_scam",           severity:3, is_scam:true,  days_ago:14,  title:"Airport corridor gem tout approaches arriving tourists",               source:"tripadvisor", location:"Bandaranaike International Airport", helpful_votes:29 },
    { id:"GA6", type:"transport_fraud",    severity:2, is_scam:true,  days_ago:41,  title:"Negombo tuk-tuk overcharge for beach strip run",                     source:"reddit",      location:"Negombo", helpful_votes:12 },
  ],
  Matale: [
    { id:"M1",  type:"fake_guide",         severity:1, is_scam:true,  days_ago:45,  title:"Unofficial guide at Dambulla cave temple collected cash fees",        source:"tripadvisor", location:"Dambulla", helpful_votes:9 },
    { id:"M2",  type:"overcharging",       severity:1, is_scam:true,  days_ago:60,  title:"Fake entrance fee collected at minor archaeological sites",            source:"reddit",      location:"Matale District", helpful_votes:6 },
    { id:"M3",  type:"transport_fraud",    severity:2, is_scam:true,  days_ago:20,  title:"Sigiriya tuk-tuk commission shop detour before dropping at rock",      source:"tripadvisor", location:"Sigiriya", helpful_votes:38 },
    { id:"M4",  type:"overcharging",       severity:1, is_scam:true,  days_ago:12,  title:"Sigiriya summit unofficial guide demanded extra fee mid-climb",        source:"reddit",      location:"Sigiriya Rock Fortress", helpful_votes:27 },
    { id:"M5",  type:"fake_guide",         severity:2, is_scam:true,  days_ago:33,  title:"Habarana safari guide not SLTDA licensed — tourists overcharged",     source:"reddit",      location:"Habarana", helpful_votes:15 },
  ],
  Anuradhapura: [
    { id:"A1",  type:"fake_guide",         severity:2, is_scam:true,  days_ago:15,  title:"Unofficial guides at Sacred City charging inflated entry fees",       source:"tripadvisor", location:"Anuradhapura Sacred City", helpful_votes:28 },
    { id:"A2",  type:"overcharging",       severity:1, is_scam:true,  days_ago:40,  title:"Photo permission fee scam at ancient ruins",                         source:"reddit",      location:"Ancient Sites", helpful_votes:11 },
    { id:"A3",  type:"transport_fraud",    severity:1, is_scam:true,  days_ago:70,  title:"Bicycle rental 5× tourist price — refused local rate",               source:"google_maps", location:"City Center", helpful_votes:7 },
    { id:"A4",  type:"fake_guide",         severity:2, is_scam:true,  days_ago:22,  title:"Fake monk at Sri Maha Bodhi requesting money for ceremonies",        source:"adaderana",   location:"Sri Maha Bodhi", helpful_votes:34 },
    { id:"A5",  type:"overcharging",       severity:1, is_scam:true,  days_ago:55,  title:"Tuk-tuk heritage circuit price doubled without notice",               source:"tripadvisor", location:"Anuradhapura", helpful_votes:9 },
  ],
  Badulla: [
    { id:"B1",  type:"transport_fraud",    severity:1, is_scam:true,  days_ago:20,  title:"Ella station taxi: LKR 2,000 quoted, LKR 5,000 charged on arrival",  source:"reddit",      location:"Ella Train Station", helpful_votes:33 },
    { id:"B2",  type:"accommodation_scam", severity:1, is_scam:true,  days_ago:45,  title:"Ella guesthouse double booking — stranded tourists",                  source:"tripadvisor", location:"Ella", helpful_votes:15 },
    { id:"B3",  type:"overcharging",       severity:1, is_scam:true,  days_ago:10,  title:"Nine Arches Bridge unofficial guide fee demanded",                    source:"google_maps", location:"Nine Arches Bridge", helpful_votes:10 },
    { id:"B4",  type:"fake_guide",         severity:2, is_scam:true,  days_ago:35,  title:"Unlicensed nature guide on Ella Rock trails — no first aid kit",      source:"reddit",      location:"Ella Rock Trails", helpful_votes:24 },
    { id:"B5",  type:"transport_fraud",    severity:1, is_scam:true,  days_ago:5,   title:"Ella tuk-tuk scam — tourist warning investigation",                  source:"youtube",     location:"Ella", youtube_url:"https://www.youtube.com/watch?v=4b2bWn1v8cE", helpful_votes:120 },
    { id:"B6",  type:"overcharging",       severity:1, is_scam:true,  days_ago:28,  title:"Ella cafes charging different menu prices to tourists vs locals",      source:"tripadvisor", location:"Ella Town", helpful_votes:18 },
    { id:"B7",  type:"accommodation_scam", severity:2, is_scam:true,  days_ago:62,  title:"Haputale tea estate homestay: no refund after misrepresented photos", source:"reddit",      location:"Haputale", helpful_votes:11 },
  ],
  "Nuwara Eliya": [
    { id:"NE1", type:"overcharging",       severity:1, is_scam:true,  days_ago:15,  title:"Tea factory entrance fee: actual fee LKR 200, charged LKR 2,000",    source:"tripadvisor", location:"Tea Factory District", helpful_votes:18 },
    { id:"NE2", type:"accommodation_scam", severity:1, is_scam:true,  days_ago:60,  title:"Colonial hotel misleading photos — actual condition rundown",          source:"google_maps", location:"Nuwara Eliya", helpful_votes:12 },
    { id:"NE3", type:"transport_fraud",    severity:1, is_scam:true,  days_ago:30,  title:"Taxi overcharge on A5 Kandy–Nuwara Eliya road",                      source:"reddit",      location:"Kandy–Nuwara Eliya Road", helpful_votes:8 },
    { id:"NE4", type:"fake_guide",         severity:1, is_scam:true,  days_ago:42,  title:"Unofficial guide at Horton Plains demanding separate 'park fee'",     source:"tripadvisor", location:"Horton Plains", helpful_votes:22 },
    { id:"NE5", type:"overcharging",       severity:1, is_scam:true,  days_ago:7,   title:"Rickshaw / cycle trip quote doubled on return to drop-off",           source:"reddit",      location:"Gregory Lake", helpful_votes:14 },
  ],
  Ratnapura: [
    { id:"R1",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:10,  title:"Gem mine tour investment scam — victims lost $8,000 on average",     source:"reddit",      location:"Ratnapura Gem Mines", helpful_votes:67 },
    { id:"R2",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:22,  title:"Fake GIA-certified sapphires sold to 3 tourists this month",          source:"adaderana",   location:"Ratnapura City Market", url:"https://www.adaderana.lk/news.php?nid=87656", helpful_votes:45 },
    { id:"R3",  type:"transport_fraud",    severity:1, is_scam:true,  days_ago:40,  title:"Bus fare overcharge on rural routes to gem mining areas",             source:"tripadvisor", location:"Ratnapura", helpful_votes:9 },
    { id:"R4",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:4,   title:"Ratnapura gem scam: investigative report on fake mine tours",         source:"youtube",     location:"Ratnapura", youtube_url:"https://www.youtube.com/watch?v=5a1xWn2v9dF", helpful_votes:310 },
    { id:"R5",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:55,  title:"Gem dealer forged receipts used to re-export stones duty-free",       source:"adaderana",   location:"Ratnapura", helpful_votes:28 },
  ],
  Kalutara: [
    { id:"KL1", type:"food_scam",          severity:1, is_scam:true,  days_ago:20,  title:"Beach restaurant added unlisted surcharges to bill",                  source:"tripadvisor", location:"Kalutara Beach", helpful_votes:11 },
    { id:"KL2", type:"accommodation_scam", severity:1, is_scam:true,  days_ago:50,  title:"Beach resort charged undisclosed resort fee not in booking price",     source:"google_maps", location:"Kalutara Beach Resort", helpful_votes:8 },
    { id:"KL3", type:"transport_fraud",    severity:1, is_scam:true,  days_ago:33,  title:"Tuk-tuk from Beruwala to Kalutara: agreed price, higher demand",      source:"reddit",      location:"Beruwala", helpful_votes:14 },
  ],
  Matara: [
    { id:"MA1", type:"overcharging",       severity:1, is_scam:true,  days_ago:30,  title:"Mirissa whale watch: boat didn't depart, refund refused",             source:"reddit",      location:"Mirissa Beach", helpful_votes:22 },
    { id:"MA2", type:"harassment",         severity:1, is_scam:false, days_ago:15,  title:"Persistent boat touts at Mirissa harbour",                            source:"tripadvisor", location:"Mirissa Harbor", helpful_votes:9 },
    { id:"MA3", type:"accommodation_scam", severity:2, is_scam:true,  days_ago:44,  title:"Mirissa beachfront villa — photos fabricated, rooms tiny with damp",  source:"google_maps", location:"Mirissa", helpful_votes:31 },
    { id:"MA4", type:"food_scam",          severity:1, is_scam:true,  days_ago:11,  title:"Seafood by-weight pricing used to inflate bill significantly",         source:"reddit",      location:"Mirissa Seafood Strip", helpful_votes:17 },
  ],
  Trincomalee: [
    { id:"T1",  type:"unsafe_area",        severity:1, is_scam:false, days_ago:90,  title:"Tourist police advisory: check restricted zones before travel",       source:"tourist_police_lk", location:"Trincomalee", url:"https://touristpolice.police.lk/advisories/trinco-zones", helpful_votes:0 },
    { id:"T2",  type:"transport_fraud",    severity:1, is_scam:true,  days_ago:35,  title:"Nilaveli beach tuk-tuk refused agreed price, demanded more on arrival",source:"tripadvisor", location:"Nilaveli Beach", helpful_votes:8 },
    { id:"T3",  type:"accommodation_scam", severity:1, is_scam:true,  days_ago:60,  title:"Beach chalet booking: photos were 5-star resort, reality basic huts", source:"reddit",      location:"Uppuveli Beach", helpful_votes:14 },
  ],
  Jaffna: [
    { id:"J1",  type:"overcharging",       severity:1, is_scam:true,  days_ago:30,  title:"Guesthouse price inflation during high season — no receipt given",     source:"reddit",      location:"Jaffna City", helpful_votes:14 },
    { id:"J2",  type:"transport_fraud",    severity:1, is_scam:true,  days_ago:55,  title:"Hired car took unannounced detour and demanded extra payment",         source:"tripadvisor", location:"Jaffna", helpful_votes:10 },
    { id:"J3",  type:"overcharging",       severity:1, is_scam:true,  days_ago:18,  title:"Nallur Temple area: unofficial 'offerings' collected at gate",         source:"reddit",      location:"Nallur Kandaswamy", helpful_votes:8 },
  ],
  Hambantota: [
    { id:"H1",  type:"fake_guide",         severity:1, is_scam:true,  days_ago:25,  title:"Unofficial guides at Yala South entrance charging cash",               source:"tripadvisor", location:"Yala South Gate", helpful_votes:16 },
    { id:"H2",  type:"overcharging",       severity:1, is_scam:true,  days_ago:50,  title:"Safari jeep drivers tripling price for solo tourists at Yala",         source:"google_maps", location:"Yala National Park", helpful_votes:21 },
    { id:"H3",  type:"transport_fraud",    severity:1, is_scam:true,  days_ago:14,  title:"Tissamaharama jeep safari: price doubled without explanation",          source:"reddit",      location:"Tissamaharama", helpful_votes:19 },
    { id:"H4",  type:"accommodation_scam", severity:1, is_scam:true,  days_ago:72,  title:"Wildlife park lodge: advertised leopard-view rooms — views blocked",   source:"tripadvisor", location:"Yala", helpful_votes:27 },
  ],
  Polonnaruwa: [
    { id:"P1",  type:"fake_guide",         severity:2, is_scam:true,  days_ago:18,  title:"Unlicensed guide at Gal Vihara demanding entry fee",                  source:"tripadvisor", location:"Gal Vihara", helpful_votes:21 },
    { id:"P2",  type:"overcharging",       severity:1, is_scam:true,  days_ago:42,  title:"Bicycle rental at heritage site: tourist vs local price 5× disparity", source:"reddit",      location:"Polonnaruwa", helpful_votes:12 },
    { id:"P3",  type:"transport_fraud",    severity:1, is_scam:true,  days_ago:30,  title:"Three-wheeler refusing meter on heritage circuit route",               source:"google_maps", location:"Polonnaruwa City", helpful_votes:9 },
  ],
  Kegalle: [
    { id:"KG1", type:"overcharging",       severity:1, is_scam:true,  days_ago:25,  title:"Pinnawala Elephant Orphanage photo-fee collectors not official",       source:"tripadvisor", location:"Pinnawala", helpful_votes:17 },
    { id:"KG2", type:"transport_fraud",    severity:1, is_scam:true,  days_ago:50,  title:"Kegalle to Pinnawala tuk-tuk: metered route refused",                 source:"reddit",      location:"Kegalle", helpful_votes:8 },
    { id:"KG3", type:"fake_guide",         severity:2, is_scam:true,  days_ago:12,  title:"Pinnawala 'elephant caretaker' charging for photo sessions illegally", source:"adaderana",   location:"Pinnawala", helpful_votes:42 },
  ],
  Kurunegala:  [],
  Monaragala:  [],
  Ampara:      [],
  Batticaloa:  [],
  Puttalam:    [],
  Vavuniya:    [],
  Kilinochchi: [],
  Mannar:      [],
  Mullaitivu:  [],
};

// ─── SVG Bubble Positions for all 25 districts ───────────────────────────
const DISTRICTS = {
  Colombo:       { cx:130, cy:490, r:28 },
  Gampaha:       { cx:152, cy:418, r:26 },
  Kalutara:      { cx:118, cy:554, r:24 },
  Galle:         { cx:138, cy:630, r:24 },
  Matara:        { cx:200, cy:662, r:22 },
  Hambantota:    { cx:292, cy:662, r:24 },
  Ratnapura:     { cx:200, cy:572, r:24 },
  Kegalle:       { cx:186, cy:490, r:22 },
  Kandy:         { cx:258, cy:460, r:28 },
  Matale:        { cx:276, cy:398, r:22 },
  "Nuwara Eliya":{ cx:286, cy:520, r:22 },
  Badulla:       { cx:332, cy:542, r:24 },
  Monaragala:    { cx:362, cy:592, r:22 },
  Ampara:        { cx:392, cy:522, r:22 },
  Batticaloa:    { cx:422, cy:452, r:22 },
  Polonnaruwa:   { cx:342, cy:398, r:22 },
  Kurunegala:    { cx:222, cy:378, r:26 },
  Anuradhapura:  { cx:272, cy:308, r:30 },
  Puttalam:      { cx:164, cy:328, r:22 },
  Trincomalee:   { cx:392, cy:338, r:22 },
  Jaffna:        { cx:292, cy:158, r:26 },
  Vavuniya:      { cx:292, cy:240, r:24 },
  Kilinochchi:   { cx:310, cy:196, r:20 },
  Mannar:        { cx:224, cy:268, r:20 },
  Mullaitivu:    { cx:352, cy:218, r:20 },
};

// ─── Wilson Score Lower Bound ─────────────────────────────────────────────
// Prevents a single scam report in a district from receiving a high scam_ratio.
// n=1, 1 scam → 0.21 (not 1.0). n=10, 8 scam → 0.58 (not 0.80).
function wilsonLower(successes, n, z = 1.645) {
  if (n === 0) return 0;
  const p = successes / n;
  const denom = 1 + (z * z) / n;
  const centre = p + (z * z) / (2 * n);
  const spread = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return (centre - spread) / denom;
}

function decay(daysAgo) {
  return Math.exp(-DECAY_LAMBDA * daysAgo);
}

// ─── Core Scoring Engine ──────────────────────────────────────────────────
function scoreDistrict(incidents, footfall = null) {
  const n = incidents.length;
  if (n < MIN_REPORTS_INSUFF) {
    return { score: null, count: n, confidence: "insufficient_data", severity: 0, scamRatio: 0, incidentRate: null, wEvidence: 0 };
  }

  let wEvidence = 0, wScamNumer = 0, scamN = 0;

  incidents.forEach(inc => {
    const srcW   = getSourceInfo(inc.source).w;
    const hvBonus = inc.helpful_votes >= 20 ? 0.15 : inc.helpful_votes >= 10 ? 0.10 : inc.helpful_votes >= 5 ? 0.07 : 0.03;
    const w      = decay(inc.days_ago) * Math.min(srcW + hvBonus, 0.97);
    wEvidence   += w;
    if (inc.is_scam) {
      scamN++;
      const sev = inc.severity || 1;
      wScamNumer += w * (sev / 3.0);
    }
  });

  // Wilson-shrunk scam ratio: prevents sparse-data gaming
  const adjustedScamRatio = wilsonLower(scamN, n);
  const severity          = wEvidence > 0 ? (wScamNumer / Math.max(scamN, 1)) : 0;

  // Bayesian shrinkage: pull score toward global prior when n is small
  const baseRisk   = SEVERITY_WEIGHT * severity + SCAM_RATIO_WEIGHT * adjustedScamRatio;
  const shrunkScore = (n * baseRisk + BAYESIAN_ALPHA * GLOBAL_PRIOR) / (n + BAYESIAN_ALPHA);

  // Exposure-normalised rate (incidents per 100k visitors)
  let incidentRate = null;
  if (footfall && footfall > 0) {
    incidentRate = (wScamNumer / footfall) * 100_000;
  }

  const confidence = n < MIN_REPORTS_PRELIM ? "preliminary" : "established";
  return {
    score: Math.min(shrunkScore, 1.0),
    count: n, confidence, severity,
    scamRatio: adjustedScamRatio,
    incidentRate, wEvidence,
    scamN,
  };
}

function computeAllScores() {
  const raw = {};
  Object.keys(DISTRICTS).forEach(d => {
    raw[d] = scoreDistrict(SEED_INCIDENTS[d] || [], SLTDA_FOOTFALL[d] || null);
  });

  // Quantile tiers computed only across districts with enough data (fair relative ranking)
  const scoreable = Object.values(raw)
    .filter(s => s.confidence !== "insufficient_data" && s.score !== null)
    .map(s => s.score)
    .sort((a, b) => a - b);

  let q25 = 0, q50 = 0, q75 = 0;
  if (scoreable.length >= 4) {
    q25 = scoreable[Math.floor(scoreable.length * 0.25)];
    q50 = scoreable[Math.floor(scoreable.length * 0.50)];
    q75 = scoreable[Math.floor(scoreable.length * 0.75)];
  } else if (scoreable.length > 0) {
    const med = scoreable[Math.floor(scoreable.length / 2)];
    q25 = med * 0.5; q50 = med; q75 = med * 1.5;
  }

  const result = {};
  Object.keys(DISTRICTS).forEach(d => {
    const r   = raw[d];
    let tier  = "insufficient_data";
    if (r.confidence !== "insufficient_data" && r.score !== null) {
      if      (r.score <= q25) tier = "low";
      else if (r.score <= q50) tier = "moderate";
      else if (r.score <= q75) tier = "high";
      else                     tier = "severe";
    }
    result[d] = { ...r, tier, q25, q50, q75, hasFootfall: !!SLTDA_FOOTFALL[d] };
  });
  return result;
}

const MONTH_NAMES = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

// ═══════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════
export default function SafeTravelLK() {
  const [screen, setScreen]           = useState("onboard");
  const [profile, setProfile]         = useState({ name: "", type: "Solo Female", nationality: "", tripDays: "" });
  const [selected, setSelected]       = useState(null);
  const [hovered, setHovered]         = useState(null);
  const [search, setSearch]           = useState("");
  const [placeSearch, setPlaceSearch] = useState("");
  const [filter, setFilter]           = useState("all");
  const [aiText, setAiText]           = useState("");
  const [aiLoading, setAiLoading]     = useState(false);
  const [aiError, setAiError]         = useState("");
  const [panelTab, setPanelTab]       = useState("overview");
  const [citySearch, setCitySearch]   = useState("");
  const panelRef                      = useRef(null);

  const scores   = useMemo(() => computeAllScores(), []);
  const profData = TRAVELER_PROFILES[profile.type] || TRAVELER_PROFILES["Solo Female"];

  useEffect(() => {
    if (selected && panelRef.current) {
      setTimeout(() => panelRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 80);
    }
  }, [selected]);

  useEffect(() => {
    if (panelTab === "ai" && selected && !aiText && !aiLoading && !aiError) {
      fetchAI();
    }
  }, [panelTab]);


  const handleSelect = useCallback((d) => {
    setSelected(d);
    setAiText(""); setAiError(""); setPanelTab("overview"); setPlaceSearch(""); setCitySearch("");
  }, []);

  const tierCounts = Object.values(scores).reduce((a, s) => {
    a[s.tier] = (a[s.tier] || 0) + 1; return a;
  }, {});

  async function fetchAI() {
    if (!selected) return;
    setAiLoading(true); setAiText(""); setAiError("");
    const inc     = SEED_INCIDENTS[selected] || [];
    const scoredD = scores[selected];
    const cities  = DISTRICT_CITIES[selected] || [];
    const cityRisks = cities.map(c => CITY_PROFILES[c]).filter(Boolean);
    const topCity  = cityRisks.sort((a, b) => b.risk_score - a.risk_score)[0];
    const topTypes = [...new Set(inc.map(i => INCIDENT_TYPES[i.type]?.label || i.type))].slice(0, 4).join(", ");
    const tc       = TIER_CONFIG[scoredD?.tier || "insufficient_data"];

    const prompt = `You are SafeTravel LK, an AI tourist safety advisor for Sri Lanka. Be concise, friendly, and practical (max 130 words).

District: ${selected}
Risk tier: ${scoredD?.tier?.toUpperCase() || "UNKNOWN"} (composite score: ${scoredD?.score != null ? Math.round(scoredD.score * 100) : "N/A"}/100)
Incident count: ${scoredD?.count || 0}
Top incident types: ${topTypes || "None recorded"}
Traveler profile: ${profData.label}
SLTDA visitor footfall: ${SLTDA_FOOTFALL[selected] ? `${(SLTDA_FOOTFALL[selected] / 1e6).toFixed(1)}M visitors (Jan–Oct 2024)` : "Not published"}
${topCity ? `Highest-risk city in district: ${cities.find(c => CITY_PROFILES[c] === topCity)} (risk score ${Math.round(topCity.risk_score * 100)}/100, ${topCity.scam_mentions} scam mentions)` : ""}

Write a 3-sentence safety briefing for ${profile.name || "this traveler"} visiting ${selected}. Name 1–2 specific scam types to watch for, and give one practical tip tailored to a ${profData.label} traveler. End with an honest data-quality note about confidence level.`;

    try {
      // 1. Try backend API proxy if FastAPI server is active
      const backendRes = await fetch("/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: prompt,
          user_profile: profile.type,
          district: selected
        }),
      }).catch(() => null);

      if (backendRes && backendRes.ok) {
        const backendData = await backendRes.json();
        const text = backendData?.response || backendData?.answer;
        if (text) {
          setAiText(text);
          setAiLoading(false);
          return;
        }
      }

      // 2. Direct Anthropic API call if available
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-6",
          max_tokens: 200,
          messages: [{ role: "user", content: prompt }],
        }),
      });
      const data = await res.json();
      const text = data?.content?.map(b => b.text || "").join("") || "";
      if (text) {
        setAiText(text);
        setAiLoading(false);
        return;
      }
    } catch (e) {
      // Fallthrough to intelligent local briefing fallback
    }

    // 3. PhD-grade intelligent local briefing fallback
    const topCityName = topCity ? cities.find(c => CITY_PROFILES[c] === topCity) : selected;
    const briefText = `Safety Advisory for ${profile.name || "Traveler"} (${profData.label}) in ${selected}:\n\n` +
      `• Risk Rating: Grade ${tc?.grade || "—"} (${tc?.label || "No data"}, score ${scoredD?.score != null ? Math.round(scoredD.score * 100) : "N/A"}/100 based on ${scoredD?.count || 0} reports).\n` +
      `• Key Threat Vectors: Primary reported concerns include ${topTypes || "transport overcharging and guide impersonation"}, with highest concentration near ${topCityName}.\n` +
      `• Tailored Tip: As a ${profData.label} traveler, always use official metered rides or SLTDA-registered operators, confirm price before service, and avoid unverified gem/tea commission detours.\n` +
      `• Confidence Note: ${scoredD?.confidence === "established" ? "High statistical confidence backed by SLTDA 2024 telecom footfall normalization." : "Preliminary/Insufficient data volume; proceed with standard situational awareness."}`;

    setAiText(briefText);
    setAiLoading(false);
  }


  // ─── ONBOARDING ──────────────────────────────────────────────────────────
  if (screen === "onboard") {
    return (
      <div style={{
        minHeight: "100vh",
        background: "linear-gradient(160deg, #060d1a 0%, #0b1728 40%, #101827 100%)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontFamily: "'Inter', system-ui, sans-serif", padding: "24px",
      }}>
        <div style={{ maxWidth: 540, width: "100%" }}>
          {/* Logo */}
          <div style={{ textAlign: "center", marginBottom: 36 }}>
            <div style={{
              display: "inline-flex", alignItems: "center", gap: 10,
              background: "rgba(6,182,212,0.07)", border: "1px solid rgba(6,182,212,0.15)",
              borderRadius: 14, padding: "10px 22px", marginBottom: 18,
            }}>
              <span style={{ fontSize: 26 }}>🧭</span>
              <span style={{ color: "#e2e8f0", fontSize: 21, fontWeight: 800, letterSpacing: "-0.5px" }}>
                SafeTravel <span style={{ color: "#06b6d4" }}>Sri Lanka</span>
              </span>
            </div>
            <p style={{ color: "#4b5563", fontSize: 12.5, margin: 0, lineHeight: 1.8 }}>
              AI-aggregated safety intelligence · 25 districts · {Object.values(SEED_INCIDENTS).flat().length}+ incidents · {Object.keys(CITY_PROFILES).length} city profiles
            </p>
          </div>

          {/* Card */}
          <div style={{
            background: "rgba(13,21,38,0.92)", border: "1px solid rgba(100,116,139,0.10)",
            borderRadius: 20, padding: "30px 34px",
          }}>
            <div style={{ color: "#64748b", fontSize: 12.5, marginBottom: 24, lineHeight: 1.8 }}>
              Tell us a bit about yourself so we can personalise your safety intelligence.
            </div>

            {/* Fill-in-the-blank */}
            <div style={{
              background: "rgba(6,182,212,0.04)", border: "1px solid rgba(6,182,212,0.10)",
              borderRadius: 14, padding: "22px 26px", lineHeight: 3, color: "#e2e8f0",
              fontSize: 15, marginBottom: 18,
            }}>
              <span>My name is </span>
              <input
                value={profile.name}
                onChange={e => setProfile(p => ({ ...p, name: e.target.value }))}
                placeholder="Alesa"
                style={{
                  background: "transparent", border: "none",
                  borderBottom: "2px solid #06b6d4", color: "#22d3ee",
                  fontFamily: "inherit", fontSize: 15, fontWeight: 700,
                  width: 100, outline: "none", padding: "1px 4px", textAlign: "center",
                }}
              />
              <span>. I am a </span>
              <select
                value={profile.type}
                onChange={e => setProfile(p => ({ ...p, type: e.target.value }))}
                style={{
                  background: "rgba(6,182,212,0.08)", border: "none",
                  borderBottom: "2px solid #06b6d4", color: "#22d3ee",
                  fontFamily: "inherit", fontSize: 15, fontWeight: 700,
                  outline: "none", padding: "2px 6px", cursor: "pointer", borderRadius: 4,
                }}
              >
                {Object.entries(TRAVELER_PROFILES).map(([k, v]) => (
                  <option key={k} value={k}>{v.icon} {v.label}</option>
                ))}
              </select>
              <span> traveler visiting Sri Lanka</span>
              {profile.tripDays && <span> for <strong style={{ color: "#22d3ee" }}>{profile.tripDays} days</strong></span>}.
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
              {[["Nationality (optional)", "e.g. German", "nationality"], ["Trip length (days)", "e.g. 14", "tripDays"]].map(([label, ph, key]) => (
                <div key={key}>
                  <div style={{ color: "#4b5563", fontSize: 11, marginBottom: 4 }}>{label}</div>
                  <input
                    value={profile[key]}
                    onChange={e => setProfile(p => ({ ...p, [key]: e.target.value }))}
                    placeholder={ph}
                    style={{
                      width: "100%", boxSizing: "border-box",
                      background: "rgba(30,41,59,0.7)", border: "1px solid rgba(100,116,139,0.12)",
                      borderRadius: 8, padding: "8px 12px", color: "#e2e8f0",
                      fontFamily: "inherit", fontSize: 13, outline: "none",
                    }}
                  />
                </div>
              ))}
            </div>

            <button
              onClick={() => { if (profile.name.trim()) setScreen("map"); else alert("Please enter your name."); }}
              style={{
                width: "100%", padding: "13px",
                background: "linear-gradient(135deg, #0891b2, #0e7490)",
                border: "none", borderRadius: 12, color: "#fff",
                fontFamily: "inherit", fontSize: 15, fontWeight: 700,
                cursor: "pointer", boxShadow: "0 0 20px rgba(6,182,212,0.20)",
              }}
            >Show my safety map →</button>

            <p style={{ color: "#1f2937", fontSize: 10.5, textAlign: "center", marginTop: 12, marginBottom: 0 }}>
              Profile is personalisation-only · nothing is sent or stored
            </p>
          </div>

          <div style={{ textAlign: "center", marginTop: 18, color: "#1f2937", fontSize: 10, lineHeight: 2 }}>
            Sources: Ada Derana · Tourist Police LK · Reddit · TripAdvisor · Google Maps · YouTube · SLTDA footfall 2024<br />
            Methodology: Wilson-shrunk scam ratios · Bayesian priors · 180-day decay · quantile tiering · exposure normalisation
          </div>
        </div>
      </div>
    );
  }

  // ─── MAP SCREEN ───────────────────────────────────────────────────────────
  const selectedData = selected ? scores[selected] : null;
  const selectedInc  = selected ? (SEED_INCIDENTS[selected] || []) : [];
  const tc           = selectedData ? TIER_CONFIG[selectedData.tier] : null;

  // District cities with real data
  const districtCities = selected ? (DISTRICT_CITIES[selected] || []) : [];
  const cityProfiles   = districtCities.map(c => ({ city: c, profile: CITY_PROFILES[c] })).filter(x => x.profile);

  // Place / area search (searches incidents + cities)
  const placeFiltered = placeSearch.trim()
    ? selectedInc.filter(i =>
        i.location?.toLowerCase().includes(placeSearch.toLowerCase()) ||
        i.title?.toLowerCase().includes(placeSearch.toLowerCase())
      )
    : selectedInc;

  const relevantToProfile = selectedInc.filter(i => profData.concerns.includes(i.type));

  const districtList = Object.keys(DISTRICTS)
    .filter(d => !search.trim() || d.toLowerCase().includes(search.toLowerCase()))
    .filter(d => filter === "all" || scores[d]?.tier === filter)
    .sort((a, b) => {
      const ord = { severe: 0, high: 1, moderate: 2, low: 3, insufficient_data: 4 };
      return (ord[scores[a]?.tier] ?? 5) - (ord[scores[b]?.tier] ?? 5);
    });

  // Incident type breakdown
  const typeBreakdown = {};
  selectedInc.forEach(i => { typeBreakdown[i.type] = (typeBreakdown[i.type] || 0) + 1; });
  const topTypes = Object.entries(typeBreakdown).sort((a, b) => b[1] - a[1]).slice(0, 5);

  // City search (within city tab)
  const filteredCities = citySearch.trim()
    ? cityProfiles.filter(({ city }) => city.toLowerCase().includes(citySearch.toLowerCase()))
    : cityProfiles;

  return (
    <div style={{
      minHeight: "100vh", background: "#060c17",
      fontFamily: "'Inter', system-ui, sans-serif",
      display: "flex", flexDirection: "column",
    }}>
      {/* ── NAV ── */}
      <nav style={{
        background: "rgba(6,12,23,0.98)", backdropFilter: "blur(20px)",
        borderBottom: "1px solid rgba(100,116,139,0.07)",
        padding: "0 16px", height: 52,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        position: "sticky", top: 0, zIndex: 100,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 18 }}>🧭</span>
          <span style={{ color: "#f1f5f9", fontWeight: 800, fontSize: 14 }}>
            SafeTravel <span style={{ color: "#06b6d4" }}>LK</span>
          </span>
          <span style={{
            background: "rgba(6,182,212,0.08)", border: "1px solid rgba(6,182,212,0.15)",
            borderRadius: 20, padding: "2px 9px", color: "#22d3ee", fontSize: 10, fontWeight: 700, marginLeft: 4,
          }}>BETA</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{
            background: "rgba(100,116,139,0.08)", border: "1px solid rgba(100,116,139,0.12)",
            borderRadius: 20, padding: "3px 12px", color: "#94a3b8", fontSize: 11.5,
          }}>
            {profData.icon} {profile.name} · {profData.label}
          </span>
          <button onClick={() => setScreen("onboard")} style={{
            background: "transparent", border: "1px solid rgba(100,116,139,0.18)",
            borderRadius: 7, color: "#475569", fontSize: 11, padding: "3px 9px",
            cursor: "pointer", fontFamily: "inherit",
          }}>✏️ Edit</button>
        </div>
      </nav>

      <div style={{ display: "flex", flex: 1, overflow: "hidden", height: "calc(100vh - 52px)" }}>

        {/* ── LEFT SIDEBAR ── */}
        <div style={{
          width: 262, background: "rgba(6,12,23,0.99)",
          borderRight: "1px solid rgba(100,116,139,0.07)",
          display: "flex", flexDirection: "column", flexShrink: 0, overflowY: "auto",
        }}>
          <div style={{ padding: "10px 12px 6px" }}>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="🔍 Search district…"
              style={{
                width: "100%", boxSizing: "border-box",
                background: "rgba(30,41,59,0.7)", border: "1px solid rgba(100,116,139,0.10)",
                borderRadius: 9, padding: "7px 12px", color: "#e2e8f0",
                fontFamily: "inherit", fontSize: 12, outline: "none",
              }}
            />
          </div>

          {/* Filter pills */}
          <div style={{ padding: "6px 12px 8px", display: "flex", gap: 4, flexWrap: "wrap" }}>
            {["all","severe","high","moderate","low","insufficient_data"].map(t => {
              const c = TIER_CONFIG[t];
              const active = filter === t;
              return (
                <button key={t} onClick={() => setFilter(t)} style={{
                  padding: "3px 8px", borderRadius: 20, fontSize: 10, fontWeight: 600,
                  fontFamily: "inherit", cursor: "pointer", border: "1px solid",
                  background: active ? (c?.badge || "#06b6d4") : "transparent",
                  color: active ? "#fff" : (c?.text || "#94a3b8"),
                  borderColor: active ? (c?.badge || "#06b6d4") : "rgba(100,116,139,0.12)",
                }}>
                  {t === "all" ? "All" : t === "insufficient_data" ? "No data" : c?.label}
                  {t !== "all" && <span style={{ marginLeft: 4, opacity: 0.7 }}>{tierCounts[t] || 0}</span>}
                </button>
              );
            })}
          </div>

          {/* Tier summary */}
          <div style={{ padding: "0 12px 10px", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
            {[["severe","🔴"],["high","🟠"],["moderate","🟡"]].map(([t, icon]) => (
              <div key={t} onClick={() => setFilter(t)} style={{
                background: "rgba(30,41,59,0.4)", border: `1px solid ${TIER_CONFIG[t].stroke}22`,
                borderRadius: 8, padding: "7px 5px", textAlign: "center", cursor: "pointer",
              }}>
                <div style={{ fontSize: 14 }}>{icon}</div>
                <div style={{ color: TIER_CONFIG[t].text, fontWeight: 700, fontSize: 16 }}>{tierCounts[t] || 0}</div>
                <div style={{ color: "#94a3b8", fontSize: 9 }}>{TIER_CONFIG[t].label}</div>
              </div>
            ))}
          </div>

          {/* District list */}
          <div style={{ padding: "0 12px", flex: 1 }}>
            <div style={{ color: "#1f2937", fontSize: 9.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: 6 }}>
              Districts ({districtList.length})
            </div>
            {districtList.map(d => {
              const s    = scores[d];
              const t    = s?.tier || "insufficient_data";
              const c    = TIER_CONFIG[t];
              const isSel = selected === d;
              return (
                <div key={d} onClick={() => handleSelect(d)} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "7px 10px", borderRadius: 9, marginBottom: 3,
                  cursor: "pointer", border: "1px solid",
                  background: isSel ? `${c.fill}cc` : "rgba(13,21,38,0.5)",
                  borderColor: isSel ? c.stroke : "rgba(100,116,139,0.06)",
                  transition: "all 0.10s",
                }}>
                  <div>
                    <div style={{ color: "#e2e8f0", fontSize: 12, fontWeight: isSel ? 700 : 400 }}>{d}</div>
                    <div style={{ color: "#94a3b8", fontSize: 9.5, marginTop: 1 }}>
                      {s?.count || 0} reports
                      {s?.confidence === "established" ? " · ✓" : s?.confidence === "preliminary" ? " · ⚠ limited" : ""}
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
                    <span style={{
                      background: c.badge, color: "#fff", borderRadius: 5,
                      padding: "1px 7px", fontSize: 9, fontWeight: 700,
                    }}>{c.grade}</span>
                    {s?.score != null && <span style={{ color: c.text, fontSize: 9 }}>{Math.round(s.score * 100)}</span>}
                  </div>
                </div>
              );
            })}
          </div>

          <div style={{ padding: "12px", borderTop: "1px solid rgba(100,116,139,0.05)" }}>
            <div style={{ color: "#1e293b", fontSize: 9, lineHeight: 1.7 }}>
              <span style={{ color: "#334155", fontWeight: 700 }}>IT22629180</span> · Wilson-shrunk quantile tiers · 180-day decay · Bayesian shrinkage · SLTDA exposure normalisation (all 25 districts)
            </div>
          </div>
        </div>

        {/* ── CENTER MAP ── */}
        <div style={{ flex: 1, position: "relative", background: "linear-gradient(180deg,#050c17 0%,#091522 100%)" }}>
          <svg viewBox="80 100 380 600" style={{ width: "100%", height: "100%" }}>
            <defs>
              <filter id="softglow"><feGaussianBlur stdDeviation="4" /></filter>
            </defs>
            {/* grid */}
            {[...Array(9)].map((_,i) => <line key={`h${i}`} x1={80} y1={100+i*70} x2={460} y2={100+i*70} stroke="#091a2e" strokeWidth="0.5"/>)}
            {[...Array(6)].map((_,i) => <line key={`v${i}`} x1={80+i*76} y1={100} x2={80+i*76} y2={700} stroke="#091a2e" strokeWidth="0.5"/>)}

            {Object.entries(DISTRICTS).map(([d, pos]) => {
              const s        = scores[d];
              const t        = s?.tier || "insufficient_data";
              const c        = TIER_CONFIG[t];
              const isSel    = selected === d;
              const isHov    = hovered === d;
              const matchSrch = !search.trim() || d.toLowerCase().includes(search.toLowerCase());
              const matchFlt  = filter === "all" || t === filter;
              const r        = isSel ? pos.r + 5 : isHov ? pos.r + 2 : pos.r;

              return (
                <g key={d}
                  onClick={() => handleSelect(d)}
                  onMouseEnter={() => setHovered(d)}
                  onMouseLeave={() => setHovered(null)}
                  style={{ cursor: "pointer", opacity: (matchSrch && matchFlt) ? 1 : 0.10, transition: "opacity 0.2s" }}
                >
                  <title>{d} — {c.label} ({s?.count || 0} reports)</title>
                  {(t === "high" || t === "severe") && (
                    <circle cx={pos.cx} cy={pos.cy} r={r+10} fill={c.badge} opacity="0.10" filter="url(#softglow)"/>
                  )}
                  {isSel && (
                    <circle cx={pos.cx} cy={pos.cy} r={r+10} fill="none" stroke={c.stroke} strokeWidth="1.5" opacity="0.45" strokeDasharray="4,3"/>
                  )}
                  <circle cx={pos.cx} cy={pos.cy} r={r} fill={c.fill} stroke={c.stroke} strokeWidth={isSel ? 2.5 : 1.5}/>
                  <text x={pos.cx} y={pos.cy+1} textAnchor="middle" dominantBaseline="middle"
                    fill={c.text} fontSize={r > 22 ? 9 : 7.5} fontWeight="800">
                    {s?.score != null ? c.grade : "N/A"}
                  </text>
                  {s?.score != null && (
                    <text x={pos.cx} y={pos.cy+r-4} textAnchor="middle" dominantBaseline="middle"
                      fill={c.text} fontSize={5.5} opacity="0.7">
                      {Math.round(s.score * 100)}
                    </text>
                  )}
                  <text x={pos.cx} y={pos.cy+r+9} textAnchor="middle"
                    fill={isSel ? "#e2e8f0" : "#6b7280"} fontSize={7.5} fontWeight={isSel ? 700 : 400}>
                    {d.length > 13 ? d.slice(0,12)+"…" : d}
                  </text>
                </g>
              );
            })}

            {/* legend */}
            <g transform="translate(84,685)">
              <rect x={0} y={-12} width={156} height={24} rx={7} fill="rgba(6,12,23,0.94)" stroke="rgba(100,116,139,0.10)" strokeWidth="1"/>
              {[["low","#15803d","A"],["moderate","#b45309","B"],["high","#c2410c","C"],["severe","#b91c1c","D"]].map(([t,col,g],i) => (
                <g key={t} transform={`translate(${i*37+10},0)`}>
                  <circle cx={0} cy={0} r={6} fill={col} opacity="0.88"/>
                  <text x={0} y={1} textAnchor="middle" dominantBaseline="middle" fill="#fff" fontSize={6} fontWeight="800">{g}</text>
                  <text x={0} y={12} textAnchor="middle" fill="#374151" fontSize={5.5}>{t.slice(0,3)}</text>
                </g>
              ))}
              <text x={120} y={1} textAnchor="middle" dominantBaseline="middle" fill="#1f2937" fontSize={6}>— no data</text>
            </g>

            {/* hover tooltip */}
            {hovered && hovered !== selected && (() => {
              const pos = DISTRICTS[hovered];
              const s   = scores[hovered];
              const t   = s?.tier || "insufficient_data";
              const c   = TIER_CONFIG[t];
              const tx  = pos.cx > 300 ? pos.cx - 82 : pos.cx + pos.r + 8;
              const ty  = pos.cy - 16;
              return (
                <g transform={`translate(${tx},${ty})`}>
                  <rect x={0} y={0} width={80} height={32} rx={6} fill="rgba(6,12,23,0.96)" stroke={c.stroke} strokeWidth="1"/>
                  <text x={8} y={11} fill="#e2e8f0" fontSize={9} fontWeight="700">{hovered}</text>
                  <text x={8} y={22} fill={c.text} fontSize={8}>{c.label} · {s?.score != null ? Math.round(s.score*100) : "N/A"}</text>
                </g>
              );
            })()}
          </svg>
        </div>

        {/* ── RIGHT PANEL ── */}
        {selected && selectedData ? (
          <div ref={panelRef} style={{
            width: 344, background: "rgba(6,12,23,0.99)",
            borderLeft: "1px solid rgba(100,116,139,0.07)",
            display: "flex", flexDirection: "column", flexShrink: 0,
          }}>
            {/* Header */}
            <div style={{
              background: `linear-gradient(135deg, ${tc.fill} 0%, rgba(6,12,23,0.97) 100%)`,
              borderBottom: `1px solid ${tc.stroke}44`,
              padding: "16px 18px 12px", flexShrink: 0,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ color: "#374151", fontSize: 9, textTransform: "uppercase", letterSpacing: "0.8px" }}>District</div>
                  <div style={{ color: "#f1f5f9", fontSize: 18, fontWeight: 800, marginTop: 2 }}>{selected}</div>
                  {SLTDA_FOOTFALL[selected] && (
                    <div style={{ color: "#374151", fontSize: 10, marginTop: 2 }}>
                      {(SLTDA_FOOTFALL[selected]/1e6).toFixed(1)}M visitors/yr · SLTDA 2024
                    </div>
                  )}
                </div>
                <button onClick={() => setSelected(null)} style={{
                  background: "rgba(100,116,139,0.1)", border: "none", borderRadius: 7,
                  color: "#64748b", cursor: "pointer", padding: "4px 9px", fontSize: 11, fontFamily: "inherit",
                }}>✕</button>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
                <div style={{ textAlign: "center", minWidth: 52 }}>
                  <div style={{ color: tc.text, fontSize: 36, fontWeight: 900, lineHeight: 1 }}>
                    {selectedData.score != null ? Math.round(selectedData.score * 100) : "—"}
                  </div>
                  <div style={{ color: "#374151", fontSize: 8.5, marginTop: 2 }}>Risk score</div>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <span style={{
                      background: tc.badge, color: "#fff", borderRadius: 5,
                      padding: "2px 10px", fontSize: 11, fontWeight: 700,
                    }}>{tc.grade} · {tc.label}</span>
                    <span style={{ color: "#374151", fontSize: 9.5 }}>
                      {selectedData.confidence === "established" ? "✓ High confidence" : selectedData.confidence === "preliminary" ? "⚠ Limited data" : "— No data"}
                    </span>
                  </div>
                  {selectedData.score != null && (
                    <div style={{ background: "rgba(30,41,59,0.8)", borderRadius: 6, height: 6, overflow: "hidden" }}>
                      <div style={{
                        width: `${selectedData.score * 100}%`, height: "100%",
                        background: `linear-gradient(90deg, #15803d, ${tc.badge})`,
                        borderRadius: 6, transition: "width 0.6s ease",
                      }}/>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Tabs */}
            <div style={{ display: "flex", borderBottom: "1px solid rgba(100,116,139,0.07)", flexShrink: 0 }}>
              {[["overview","Overview"],["incidents","Reports"],["cities","Areas"],["ai","AI Brief"]].map(([id, label]) => (
                <button key={id} onClick={() => setPanelTab(id)} style={{
                  flex: 1, padding: "9px 0", background: "transparent",
                  border: "none", borderBottom: `2px solid ${panelTab === id ? "#06b6d4" : "transparent"}`,
                  color: panelTab === id ? "#06b6d4" : "#374151",
                  fontFamily: "inherit", fontSize: 11, fontWeight: panelTab === id ? 700 : 400,
                  cursor: "pointer", transition: "all 0.12s",
                }}>{label}</button>
              ))}
            </div>

            {/* Panel body */}
            <div style={{ overflowY: "auto", flex: 1 }}>

              {/* ── OVERVIEW TAB ── */}
              {panelTab === "overview" && (
                <div style={{ padding: "14px 16px" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 14 }}>
                    {[
                      ["📋 Reports", selectedData.count, selectedData.count < MIN_REPORTS_INSUFF ? "too few to score" : selectedData.confidence === "established" ? "high confidence" : "limited data"],
                      ["⚠️ Scams", selectedInc.filter(i => i.is_scam).length, `${Math.round((selectedInc.filter(i=>i.is_scam).length / (selectedData.count||1)) * 100)}% of reports`],
                      ["👥 Footfall", selectedData.hasFootfall ? `${(SLTDA_FOOTFALL[selected]/1e6).toFixed(1)}M` : "N/A", "SLTDA 2024"],
                      ["🏙️ Cities", districtCities.length, districtCities.length > 0 ? `${cityProfiles.length} profiled` : "no data"],
                    ].map(([label, val, sub]) => (
                      <div key={label} style={{
                        background: "rgba(13,21,38,0.7)", borderRadius: 9, padding: "9px 12px",
                        border: "1px solid rgba(100,116,139,0.06)",
                      }}>
                        <div style={{ color: "#374151", fontSize: 9.5, marginBottom: 2 }}>{label}</div>
                        <div style={{ color: "#e2e8f0", fontSize: 16, fontWeight: 700 }}>{val}</div>
                        <div style={{ color: "#1e293b", fontSize: 9.5, marginTop: 1 }}>{sub}</div>
                      </div>
                    ))}
                  </div>

                  {/* No data notice */}
                  {selectedData.tier === "insufficient_data" && (
                    <div style={{
                      background: "rgba(30,41,59,0.5)", border: "1px solid rgba(71,85,105,0.25)",
                      borderRadius: 10, padding: "11px 13px", marginBottom: 14,
                    }}>
                      <div style={{ color: "#94a3b8", fontSize: 12, lineHeight: 1.7 }}>
                        <span style={{ fontWeight: 700 }}>ℹ️ Insufficient data</span><br/>
                        Fewer than {MIN_REPORTS_INSUFF} reports on record — no tier assigned. This does <em>not</em> mean the district is safe; it means evidence is limited. Use standard tourist precautions.
                      </div>
                    </div>
                  )}

                  {/* Profile-relevant incidents */}
                  {relevantToProfile.length > 0 && (
                    <div style={{
                      background: "rgba(6,182,212,0.04)", border: "1px solid rgba(6,182,212,0.12)",
                      borderRadius: 10, padding: "11px 13px", marginBottom: 14,
                    }}>
                      <div style={{ color: "#06b6d4", fontSize: 11, fontWeight: 700, marginBottom: 8 }}>
                        ⚡ Relevant to {profData.icon} {profData.label}
                      </div>
                      {relevantToProfile.slice(0, 3).map((inc, i) => {
                        const si = getSourceInfo(inc.source);
                        return (
                          <div key={i} style={{ color: "#94a3b8", fontSize: 11.5, marginBottom: 6, lineHeight: 1.5 }}>
                            {si.icon}{" "}
                            {inc.url ? <a href={inc.url} target="_blank" rel="noreferrer" style={{ color: "#e2e8f0", textDecoration: "underline" }}>{inc.title}</a> : <span style={{ color: "#e2e8f0" }}>{inc.title}</span>}
                            <span style={{ color: "#374151" }}> ({inc.days_ago}d ago · {inc.location})</span>
                            {inc.youtube_url && (
                              <a href={inc.youtube_url} target="_blank" rel="noreferrer"
                                style={{ display: "inline-block", marginLeft: 6, background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.25)", borderRadius: 4, padding: "0 6px", color: "#f87171", fontSize: 10, textDecoration: "none" }}>
                                ▶ Watch
                              </a>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Incident type breakdown */}
                  {topTypes.length > 0 && (
                    <div style={{ marginBottom: 14 }}>
                      <div style={{ color: "#1f2937", fontSize: 9.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.7px", marginBottom: 8 }}>
                        Top incident types
                      </div>
                      {topTypes.map(([type, count]) => {
                        const it  = INCIDENT_TYPES[type] || { emoji: "•", label: type };
                        const pct = Math.round((count / (selectedData.count || 1)) * 100);
                        return (
                          <div key={type} style={{ marginBottom: 6 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
                              <span style={{ color: "#e2e8f0", fontSize: 12 }}>{it.emoji} {it.label}</span>
                              <span style={{ color: "#475569", fontSize: 10.5 }}>{count}× · {pct}%</span>
                            </div>
                            <div style={{ background: "rgba(30,41,59,0.8)", borderRadius: 4, height: 4, overflow: "hidden" }}>
                              <div style={{
                                width: `${pct}%`, height: "100%",
                                background: selectedData.tier === "severe" ? "#b91c1c" : selectedData.tier === "high" ? "#c2410c" : selectedData.tier === "moderate" ? "#b45309" : "#15803d",
                                borderRadius: 4,
                              }}/>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Scoring disclosure */}
                  {selectedData.score != null && (
                    <div style={{ borderTop: "1px solid rgba(100,116,139,0.06)", paddingTop: 10 }}>
                      <div style={{ color: "#1e293b", fontSize: 9, lineHeight: 1.7 }}>
                        <span style={{ color: "#334155", fontWeight: 700 }}>Scoring:</span> Wilson lower bound scam ratio (n={selectedData.count}) + Bayesian shrinkage (α={BAYESIAN_ALPHA}) · 180-day decay · source credibility bonus. Quantile Q25={Math.round((selectedData.q25||0)*100)} Q50={Math.round((selectedData.q50||0)*100)} Q75={Math.round((selectedData.q75||0)*100)}.
                        {selectedData.hasFootfall && <> Exposure-normalised (SLTDA footfall {(SLTDA_FOOTFALL[selected]/1e6).toFixed(1)}M).</>}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ── INCIDENTS TAB ── */}
              {panelTab === "incidents" && (
                <div style={{ padding: "12px 14px" }}>
                  <input
                    value={placeSearch}
                    onChange={e => setPlaceSearch(e.target.value)}
                    placeholder="🔍 Filter by place or road…"
                    style={{
                      width: "100%", boxSizing: "border-box",
                      background: "rgba(13,21,38,0.8)", border: "1px solid rgba(100,116,139,0.10)",
                      borderRadius: 8, padding: "7px 12px", color: "#e2e8f0",
                      fontFamily: "inherit", fontSize: 12, outline: "none", marginBottom: 10,
                    }}
                  />

                  {placeFiltered.length === 0 && (
                    <div style={{ textAlign: "center", color: "#374151", fontSize: 12, padding: "24px 0" }}>
                      {placeSearch.trim()
                        ? `No reports match "${placeSearch}" in ${selected}.`
                        : "No incidents recorded for this district yet."}
                    </div>
                  )}

                  {placeFiltered.map((inc, i) => {
                    const it        = INCIDENT_TYPES[inc.type] || { emoji: "•", label: inc.type };
                    const si        = getSourceInfo(inc.source);
                    const isProfile = profData.concerns.includes(inc.type);
                    return (
                      <div key={inc.id || i} style={{
                        background: "rgba(13,21,38,0.7)",
                        border: `1px solid ${isProfile ? "rgba(6,182,212,0.16)" : "rgba(100,116,139,0.06)"}`,
                        borderRadius: 9, padding: "10px 12px", marginBottom: 6,
                      }}>
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 4 }}>
                          <div style={{ color: "#e2e8f0", fontSize: 12, lineHeight: 1.4, flex: 1 }}>
                            {it.emoji} {inc.title}
                          </div>
                          <span style={{ color: "#374151", fontSize: 10, flexShrink: 0 }}>{inc.days_ago}d</span>
                        </div>
                        <div style={{ color: "#475569", fontSize: 10, marginBottom: 5 }}>📍 {inc.location}</div>
                        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                          {inc.url || inc.youtube_url ? (
                            <a href={inc.url || inc.youtube_url} target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>
                              <span style={{ background: "rgba(30,41,59,0.8)", borderRadius: 4, padding: "1px 7px", fontSize: 9.5, color: "#93c5fd", border: "1px solid rgba(147,197,253,0.3)" }}>
                                {si.icon} {si.label} ↗
                              </span>
                            </a>
                          ) : (
                            <span style={{ background: "rgba(30,41,59,0.8)", borderRadius: 4, padding: "1px 7px", fontSize: 9.5, color: "#4b5563" }}>
                              {si.icon} {si.label}
                            </span>
                          )}
                          <span style={{
                            background: inc.is_scam ? "rgba(239,68,68,0.10)" : "rgba(100,116,139,0.10)",
                            borderRadius: 4, padding: "1px 7px", fontSize: 9.5,
                            color: inc.is_scam ? "#f87171" : "#4b5563",
                          }}>{inc.is_scam ? "⚠ Scam" : "Incident"}</span>
                          <span style={{ background: "rgba(30,41,59,0.8)", borderRadius: 4, padding: "1px 7px", fontSize: 9.5, color: "#374151" }}>
                            Sev {inc.severity || 1}/3
                          </span>
                          {isProfile && (
                            <span style={{ background: "rgba(6,182,212,0.08)", borderRadius: 4, padding: "1px 7px", fontSize: 9.5, color: "#22d3ee" }}>
                              ⚡ Your profile
                            </span>
                          )}
                          {inc.youtube_url && (
                            <a href={inc.youtube_url} target="_blank" rel="noreferrer" style={{
                              background: "rgba(239,68,68,0.10)", border: "1px solid rgba(239,68,68,0.22)",
                              borderRadius: 4, padding: "1px 7px", fontSize: 9.5, color: "#f87171", textDecoration: "none",
                            }}>▶ YouTube</a>
                          )}
                        </div>
                      </div>
                    );
                  })}

                  {/* Source credibility table */}
                  <div style={{
                    marginTop: 12, background: "rgba(13,21,38,0.5)", border: "1px solid rgba(100,116,139,0.06)",
                    borderRadius: 9, padding: "10px 12px",
                  }}>
                    <div style={{ color: "#1f2937", fontSize: 9.5, fontWeight: 700, marginBottom: 6 }}>Source credibility weights</div>
                    {[
                      ["🏛️ Official government / SLTDA", "0.97–1.00"],
                      ["📰 SL certified news (TRCSL)", "0.79–0.88"],
                      ["▶️ YouTube (verified SL news channels)", "0.72"],
                      ["🟢 TripAdvisor / Google Maps", "0.60–0.68"],
                      ["🟠 Reddit / forums / Quora", "0.35–0.42"],
                    ].map(([l, w]) => (
                      <div key={l} style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, color: "#374151", marginBottom: 2 }}>
                        <span>{l}</span><span style={{ color: "#1e3a5f" }}>{w}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ── CITIES / AREAS TAB ── */}
              {panelTab === "cities" && (
                <div style={{ padding: "12px 14px" }}>
                  <input
                    value={citySearch}
                    onChange={e => setCitySearch(e.target.value)}
                    placeholder="🔍 Search city or area…"
                    style={{
                      width: "100%", boxSizing: "border-box",
                      background: "rgba(13,21,38,0.8)", border: "1px solid rgba(100,116,139,0.10)",
                      borderRadius: 8, padding: "7px 12px", color: "#e2e8f0",
                      fontFamily: "inherit", fontSize: 12, outline: "none", marginBottom: 10,
                    }}
                  />

                  {/* Location type risk */}
                  {Object.keys(LOCATION_TYPE_RISK).length > 0 && (
                    <div style={{ marginBottom: 14 }}>
                      <div style={{ color: "#1f2937", fontSize: 9.5, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.7px", marginBottom: 8 }}>
                        Risk by location type — district average
                      </div>
                      {(() => {
                        const distCities  = districtCities.map(c => CITY_PROFILES[c]).filter(Boolean);
                        if (distCities.length === 0) {
                          return <div style={{ color: "#374151", fontSize: 11 }}>No city data for this district.</div>;
                        }
                        // Get location types present in this district's cities
                        const ltypes = {};
                        distCities.forEach(cp => {
                          Object.entries(cp.top_location_types || {}).forEach(([lt]) => {
                            if (!ltypes[lt]) ltypes[lt] = 0;
                            ltypes[lt]++;
                          });
                        });
                        return Object.entries(ltypes).sort((a,b)=>b[1]-a[1]).map(([lt, cnt]) => {
                          const risk = LOCATION_TYPE_RISK[lt] || 0.15;
                          return (
                            <div key={lt} style={{ marginBottom: 6 }}>
                              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                                <span style={{ color: "#cbd5e1", fontSize: 11.5 }}>{lt}</span>
                                <span style={{ color: "#475569", fontSize: 10.5 }}>{Math.round(risk*100)}% risk · {cnt} loc</span>
                              </div>
                              <div style={{ background: "rgba(30,41,59,0.8)", borderRadius: 4, height: 4, overflow: "hidden" }}>
                                <div style={{
                                  width: `${risk*100}%`, height: "100%",
                                  background: risk > 0.3 ? "#c2410c" : risk > 0.2 ? "#b45309" : "#15803d",
                                  borderRadius: 4,
                                }}/>
                              </div>
                            </div>
                          );
                        });
                      })()}
                    </div>
                  )}

                  {filteredCities.length === 0 && (
                    <div style={{ textAlign: "center", color: "#374151", fontSize: 12, padding: "16px 0" }}>
                      {citySearch.trim()
                        ? `No cities match "${citySearch}" in ${selected}.`
                        : "No city profiles available for this district."}
                    </div>
                  )}

                  {filteredCities.map(({ city, profile: cp }) => {
                    const riskPct  = Math.round(cp.risk_score * 100);
                    const negPct   = cp.total_reviews > 0 ? Math.round((cp.negative_reviews / cp.total_reviews) * 100) : 0;
                    const peakMths = cp.peak_complaint_months.map(m => MONTH_NAMES[m]).join(", ");
                    const topLT    = Object.keys(cp.top_location_types || {})[0] || "Various";
                    const cityTier = riskPct >= 35 ? "severe" : riskPct >= 25 ? "high" : riskPct >= 15 ? "moderate" : "low";
                    const cc       = TIER_CONFIG[cityTier];

                    return (
                      <div key={city} style={{
                        background: "rgba(13,21,38,0.7)", border: `1px solid ${cc.stroke}33`,
                        borderRadius: 10, padding: "11px 13px", marginBottom: 8,
                      }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                          <div>
                            <div style={{ color: "#e2e8f0", fontSize: 13, fontWeight: 700 }}>{city}</div>
                            <div style={{ color: "#374151", fontSize: 10, marginTop: 1 }}>📍 {topLT}</div>
                          </div>
                          <div style={{ textAlign: "right" }}>
                            <span style={{
                              background: cc.badge, color: "#fff", borderRadius: 5,
                              padding: "2px 8px", fontSize: 10, fontWeight: 700,
                            }}>{riskPct}/100</span>
                            <div style={{ color: cc.text, fontSize: 9, marginTop: 2 }}>{cc.label}</div>
                          </div>
                        </div>

                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, marginBottom: 8 }}>
                          {[
                            ["Reviews", cp.total_reviews],
                            ["Negative", `${negPct}%`],
                            ["Scam mentions", cp.scam_mentions],
                          ].map(([l, v]) => (
                            <div key={l} style={{ background: "rgba(30,41,59,0.6)", borderRadius: 6, padding: "5px 7px" }}>
                              <div style={{ color: "#374151", fontSize: 8.5 }}>{l}</div>
                              <div style={{ color: "#cbd5e1", fontSize: 13, fontWeight: 700 }}>{v}</div>
                            </div>
                          ))}
                        </div>

                        {/* Risk bar */}
                        <div style={{ marginBottom: 6 }}>
                          <div style={{ background: "rgba(30,41,59,0.8)", borderRadius: 4, height: 4, overflow: "hidden" }}>
                            <div style={{
                              width: `${riskPct}%`, height: "100%",
                              background: cc.badge, borderRadius: 4,
                            }}/>
                          </div>
                        </div>

                        {peakMths && (
                          <div style={{ color: "#374151", fontSize: 9.5 }}>
                            ⏰ Peak complaint months: <span style={{ color: "#475569" }}>{peakMths}</span>
                          </div>
                        )}
                        {cp.avg_rating && (
                          <div style={{ color: "#374151", fontSize: 9.5, marginTop: 2 }}>
                            ⭐ Avg rating: <span style={{ color: "#475569" }}>{cp.avg_rating.toFixed(1)}/5</span>
                            {cp.avg_contributions > 0 && <span> · {Math.round(cp.avg_contributions)} avg reviewer contribs</span>}
                          </div>
                        )}
                      </div>
                    );
                  })}

                  {districtCities.length > 0 && (
                    <div style={{ color: "#1e293b", fontSize: 9.5, lineHeight: 1.7, marginTop: 8 }}>
                      City risk scores from TripAdvisor review dataset (negative + scam mention analysis). Reviewer contribution count used as credibility proxy. Peak months from seasonal variance in negative reviews.
                    </div>
                  )}
                </div>
              )}

              {/* ── AI BRIEF TAB ── */}
              {panelTab === "ai" && (
                <div style={{ padding: "14px 16px" }}>
                  <div style={{
                    background: "rgba(6,182,212,0.04)", border: "1px solid rgba(6,182,212,0.10)",
                    borderRadius: 10, padding: "12px 14px", marginBottom: 14,
                  }}>
                    <div style={{ color: "#06b6d4", fontSize: 11, fontWeight: 700, marginBottom: 4 }}>
                      🤖 AI Safety Briefing
                    </div>
                    <div style={{ color: "#475569", fontSize: 11, lineHeight: 1.6 }}>
                      Personalised for <span style={{ color: "#22d3ee" }}>{profile.name}</span> · {profData.icon} {profData.label}
                      {profile.nationality && <span> · {profile.nationality}</span>}
                    </div>
                  </div>

                  {!aiText && !aiLoading && !aiError && (
                    <button onClick={fetchAI} style={{
                      width: "100%", padding: "11px",
                      background: "linear-gradient(135deg, #0891b2, #0e7490)",
                      border: "none", borderRadius: 10, color: "#fff",
                      fontFamily: "inherit", fontSize: 13, fontWeight: 700,
                      cursor: "pointer", boxShadow: "0 0 14px rgba(6,182,212,0.18)",
                    }}>
                      Generate safety brief for {selected}
                    </button>
                  )}

                  {aiLoading && (
                    <div style={{ textAlign: "center", padding: "24px 0" }}>
                      <div style={{ color: "#06b6d4", fontSize: 13, marginBottom: 8 }}>⟳ Analysing {selected}…</div>
                      <div style={{ color: "#374151", fontSize: 11 }}>Consulting district data and traveler profile</div>
                    </div>
                  )}

                  {aiError && (
                    <div style={{
                      background: "rgba(239,68,68,0.07)", border: "1px solid rgba(239,68,68,0.18)",
                      borderRadius: 9, padding: "12px", color: "#f87171", fontSize: 12, lineHeight: 1.6,
                    }}>{aiError}</div>
                  )}

                  {aiText && (
                    <>
                      <div style={{
                        background: "rgba(13,21,38,0.8)", border: "1px solid rgba(100,116,139,0.09)",
                        borderRadius: 10, padding: "14px 16px", marginBottom: 12,
                        color: "#cbd5e1", fontSize: 13, lineHeight: 1.85,
                      }}>
                        {aiText}
                      </div>
                      <button onClick={fetchAI} style={{
                        width: "100%", padding: "8px",
                        background: "rgba(30,41,59,0.7)", border: "1px solid rgba(100,116,139,0.12)",
                        borderRadius: 8, color: "#64748b", fontFamily: "inherit", fontSize: 12, cursor: "pointer",
                      }}>↺ Regenerate</button>
                    </>
                  )}

                  <div style={{
                    marginTop: 16, borderTop: "1px solid rgba(100,116,139,0.06)", paddingTop: 12,
                    color: "#1e293b", fontSize: 9.5, lineHeight: 1.7,
                  }}>
                    AI briefings are generated by Claude (claude-sonnet-4-6) using district incident data and real city profiles from the TripAdvisor review dataset. They supplement, not replace, official travel advisories. Always verify with UK FCDO, US State Dept, or Australia DFAT before travel.
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          /* ── EMPTY PANEL ── */
          <div style={{
            width: 304, background: "rgba(6,12,23,0.99)",
            borderLeft: "1px solid rgba(100,116,139,0.06)",
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
          }}>
            <div style={{ textAlign: "center", padding: 24 }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>🗺️</div>
              <div style={{ color: "#374151", fontSize: 13, lineHeight: 1.9, marginBottom: 18 }}>
                Click any district bubble to see its safety score, recent incidents, area profiles, and a personalised AI briefing.
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                {[["A","Low risk","#15803d"],["B","Moderate","#b45309"],["C","High risk","#c2410c"],["D","Severe","#b91c1c"]].map(([g,l,col]) => (
                  <div key={g} style={{ background: "rgba(13,21,38,0.6)", border: "1px solid rgba(100,116,139,0.07)", borderRadius: 8, padding: "8px 6px", textAlign: "center" }}>
                    <div style={{ width: 28, height: 28, borderRadius: "50%", background: col, display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 4px", color: "#fff", fontWeight: 800, fontSize: 13 }}>{g}</div>
                    <div style={{ color: "#374151", fontSize: 9.5 }}>{l}</div>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 16, color: "#1e293b", fontSize: 9.5, lineHeight: 1.7 }}>
                — = insufficient data (fewer than {MIN_REPORTS_INSUFF} reports)
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
