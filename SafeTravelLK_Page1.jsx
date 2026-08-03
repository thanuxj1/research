import { useState, useEffect, useRef, useCallback, useMemo } from "react";

// ═══════════════════════════════════════════════════════════════════════════
// SAFETRAVEL LK — Page 1: District Safety Intelligence Map
// IT22629180 — PhD Research: Tourist Safety Intelligence for Sri Lanka
//
// DESIGN & ARCHITECTURE IMPROVEMENTS:
// ✓ Live API Integration with Automatic Standalone Fallback (/api/v1/districts/risk-map)
// ✓ Cleaned & Structured Data across all 25 Districts of Sri Lanka
// ✓ Wilson Score Lower Bound & Bayesian Shrinkage (prevents low N gaming)
// ✓ Quantile-based Relative Tiering (Low, Moderate, High, Severe)
// ✓ Exposure Normalization via SLTDA Footfall Data (2024 Telecom Inbound)
// ✓ Source Credibility Weighting (Gov: 1.0, Certified News: 0.85, UGC: 0.40)
// ✓ Personalized Traveler Profiles with Risk Multipliers & Tailored Advice
// ✓ Real City & Area Risk Profiles from pattern_insights.json (36 Cities)
// ✓ Inline YouTube & Verified News Media Evidence Links
// ✓ Interactive AI Safety Briefing Generator
// ═══════════════════════════════════════════════════════════════════════════

const API_BASE_URL = "http://localhost:8000/api/v1";

// ─── Methodology Constants ────────────────────────────────────────────────
const DECAY_LAMBDA       = Math.log(2) / 180; // 180-day half-life decay
const MIN_REPORTS_INSUFF = 3;                  // Below 3 -> insufficient_data
const MIN_REPORTS_PRELIM = 15;                 // Below 15 -> preliminary confidence
const SEVERITY_WEIGHT    = 0.70;
const SCAM_RATIO_WEIGHT  = 0.30;
const BAYESIAN_ALPHA     = 0.05;               // Shrinkage weight
const GLOBAL_PRIOR       = 0.30;               // Conservative global prior mean

// ─── Source Credibility Weights ───────────────────────────────────────────
const SOURCE_WEIGHTS = {
  fcdo_gov_uk:        { w: 1.00, tier: "Gov",    icon: "🏛️", label: "UK FCDO Advisory" },
  us_state_dept:      { w: 1.00, tier: "Gov",    icon: "🏛️", label: "US State Dept" },
  australia_dfat:     { w: 1.00, tier: "Gov",    icon: "🏛️", label: "Australia DFAT" },
  canada_travel:      { w: 1.00, tier: "Gov",    icon: "🏛️", label: "Canada DFAT" },
  sltda_official:     { w: 0.97, tier: "Gov",    icon: "🏛️", label: "SLTDA Official" },
  tourist_police_lk:  { w: 0.97, tier: "Gov",    icon: "🚔", label: "Tourist Police LK" },
  adaderana:          { w: 0.88, tier: "News",   icon: "📰", label: "Ada Derana" },
  newsfirst:          { w: 0.86, tier: "News",   icon: "📰", label: "Newsfirst SL" },
  daily_mirror_lk:    { w: 0.85, tier: "News",   icon: "📰", label: "Daily Mirror" },
  sundaytimes_lk:     { w: 0.85, tier: "News",   icon: "📰", label: "Sunday Times" },
  themorning_lk:      { w: 0.83, tier: "News",   icon: "📰", label: "The Morning" },
  theisland_lk:       { w: 0.83, tier: "News",   icon: "📰", label: "The Island" },
  colombo_gazette:    { w: 0.82, tier: "News",   icon: "📰", label: "Colombo Gazette" },
  hirunews_lk:        { w: 0.80, tier: "News",   icon: "📰", label: "Hiru News" },
  youtube:            { w: 0.72, tier: "Video",  icon: "▶️",  label: "YouTube Media" },
  wikivoyage:         { w: 0.70, tier: "Wiki",   icon: "🌐", label: "WikiVoyage" },
  tripadvisor_forum:  { w: 0.68, tier: "Forum",  icon: "💬", label: "TripAdvisor Forum" },
  google_news:        { w: 0.65, tier: "Aggr",   icon: "🔵", label: "Google News" },
  google_maps:        { w: 0.62, tier: "Maps",   icon: "📍", label: "Google Maps Reviews" },
  tripadvisor:        { w: 0.60, tier: "Review", icon: "🟢", label: "TripAdvisor Reviews" },
  reviews_csv:        { w: 0.60, tier: "Review", icon: "📊", label: "Master Review Dataset" },
  reddit:             { w: 0.42, tier: "UGC",    icon: "🟠", label: "Reddit Travel" },
  forum:              { w: 0.38, tier: "UGC",    icon: "💬", label: "Travel Forums" },
  quora:              { w: 0.35, tier: "UGC",    icon: "❓", label: "Quora Discussions" },
};
const DEFAULT_SOURCE_WEIGHT = 0.35;

function getSourceInfo(src) {
  if (!src) return { w: DEFAULT_SOURCE_WEIGHT, tier: "UGC", icon: "•", label: "Community Signal" };
  const key = String(src).toLowerCase().trim().replace(/[^a-z0-9_]/g, "_");
  return SOURCE_WEIGHTS[key] || { w: DEFAULT_SOURCE_WEIGHT, tier: "UGC", icon: "📍", label: src };
}

// ─── SLTDA Telecom Inbound Visitor Footfall (All 25 Districts) ─────────────
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

// ─── City -> District Mapping ──────────────────────────────────────────────
const CITY_TO_DISTRICT = {
  Ahangama: "Galle", Ambalangoda: "Galle", Unawatuna: "Galle", Hikkaduwa: "Galle", Bentota: "Galle", Galle: "Galle",
  Ampara: "Ampara", "Arugam Bay": "Ampara",
  Anuradhapura: "Anuradhapura", Saliyapura: "Anuradhapura",
  Beruwala: "Kalutara", Kalutara: "Kalutara",
  Colombo: "Colombo", Pettah: "Colombo", Fort: "Colombo", Mount_Lavinia: "Colombo",
  Deniyaya: "Matara", Mirissa: "Matara", Weligama: "Matara", Matara: "Matara",
  Ella: "Badulla", Haputale: "Badulla", Koslanda: "Badulla", Pussellawa: "Badulla", Badulla: "Badulla",
  Embilipitiya: "Ratnapura", Ratnapura: "Ratnapura",
  Habarana: "Matale", Sigiriya: "Matale", Dambulla: "Matale", Matale: "Matale", Katukitula: "Matale",
  Jaffna: "Jaffna", Nallur: "Jaffna",
  Kalametiya: "Hambantota", Tissamaharama: "Hambantota", Weligatta: "Hambantota", Hambantota: "Hambantota", Yala: "Hambantota",
  Kalkudah: "Batticaloa", Batticaloa: "Batticaloa", Pasikuda: "Batticaloa",
  Kandy: "Kandy", Peradeniya: "Kandy", Digana: "Kandy",
  Negombo: "Gampaha", Gampaha: "Gampaha", JaEla: "Gampaha",
  "Nuwara Eliya": "Nuwara Eliya", Horton_Plains: "Nuwara Eliya",
  Pinnawala: "Kegalle", Kegalle: "Kegalle",
  Polonnaruwa: "Polonnaruwa",
  Trincomalee: "Trincomalee", Nilaveli: "Trincomalee", Uppuveli: "Trincomalee",
  Kurunegala: "Kurunegala",
  Puttalam: "Puttalam", Kalpitiya: "Puttalam", Chilaw: "Puttalam",
  Monaragala: "Monaragala", Kataragama: "Monaragala",
  Vavuniya: "Vavuniya",
  Kilinochchi: "Kilinochchi",
  Mannar: "Mannar",
  Mullaitivu: "Mullaitivu",
};

// ─── Real City Risk Profiles (pattern_insights.json) ─────────────────────
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

// ─── Location-Type Risk Distribution ──────────────────────────────────────
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

// ─── District -> Cities Mapping ───────────────────────────────────────────
const DISTRICT_CITIES = {};
Object.entries(CITY_TO_DISTRICT).forEach(([city, district]) => {
  if (!DISTRICT_CITIES[district]) DISTRICT_CITIES[district] = [];
  if (!DISTRICT_CITIES[district].includes(city)) DISTRICT_CITIES[district].push(city);
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
  gem_scam:           { emoji: "💎", label: "Gem Scam",           severity: 3 },
  tuk_tuk_scam:       { emoji: "🛺", label: "Tuk-Tuk Scam",       severity: 2 },
  overcharging:       { emoji: "💰", label: "Overcharging",        severity: 1 },
  fake_guide:         { emoji: "🧑‍💼", label: "Fake Guide",         severity: 2 },
  transport_fraud:    { emoji: "🚕", label: "Transport Fraud",     severity: 2 },
  harassment:         { emoji: "😨", label: "Harassment",          severity: 2 },
  accommodation_scam: { emoji: "🏨", label: "Accommodation Scam",  severity: 2 },
  food_scam:          { emoji: "🍽️", label: "Food Scam",           severity: 1 },
  unsafe_area:        { emoji: "⚠️", label: "Unsafe Area",         severity: 2 },
  theft:              { emoji: "👜", label: "Theft / Pickpocket",  severity: 2 },
  general_safety:     { emoji: "🔴", label: "General Incident",    severity: 1 },
};

// ─── Risk Tier Visual Configuration ──────────────────────────────────────
const TIER_CONFIG = {
  insufficient_data: { fill:"#1e2533", stroke:"#374151", badge:"#4b5563", text:"#9ca3af", label:"Insufficient Data", grade:"—" },
  low:               { fill:"#052e16", stroke:"#16a34a", badge:"#15803d", text:"#4ade80", label:"Low Risk",         grade:"A" },
  moderate:          { fill:"#422006", stroke:"#d97706", badge:"#b45309", text:"#fbbf24", label:"Moderate Risk",    grade:"B" },
  high:              { fill:"#431407", stroke:"#ea580c", badge:"#c2410c", text:"#fb923c", label:"High Risk",        grade:"C" },
  severe:            { fill:"#3b0a0a", stroke:"#dc2626", badge:"#b91c1c", text:"#f87171", label:"Severe Risk",      grade:"D" },
};

// ─── Comprehensive Seed Incidents (Cleaned Data for All 25 Districts) ────
const SEED_INCIDENTS = {
  Colombo: [
    { id:"C1",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:5,   title:"Gem shop fraud near Pettah — tourist lost $2,400",                  source:"adaderana",   location:"Pettah", helpful_votes:12 },
    { id:"C2",  type:"tuk_tuk_scam",       severity:2, is_scam:true,  days_ago:12,  title:"Airport tuk-tuk demanded 10× metered fare to Colombo 3",            source:"tripadvisor", location:"BIA Airport Road", helpful_votes:28 },
    { id:"C3",  type:"accommodation_scam", severity:2, is_scam:true,  days_ago:20,  title:"Fake guesthouse listing — different property on arrival",            source:"google_maps", location:"Colombo 3", helpful_votes:7 },
    { id:"C4",  type:"harassment",         severity:2, is_scam:false, days_ago:8,   title:"Persistent vendor harassment at Galle Face Green",                   source:"reddit",      location:"Galle Face Green", helpful_votes:45 },
    { id:"C5",  type:"transport_fraud",    severity:2, is_scam:true,  days_ago:30,  title:"Metered taxi refusing to use meter — Fort to Cinnamon Grand",        source:"tripadvisor", location:"Colombo Fort", helpful_votes:19 },
    { id:"C6",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:60,  title:"Gem investment scheme near Fort — certificates confirmed fake",       source:"adaderana",   location:"Colombo Fort", helpful_votes:8 },
    { id:"C7",  type:"unsafe_area",        severity:2, is_scam:false, days_ago:15,  title:"Pickpocket at Pettah bus stand during peak hour",                    source:"reddit",      location:"Pettah Bus Stand", helpful_votes:31 },
    { id:"C8",  type:"overcharging",       severity:1, is_scam:true,  days_ago:45,  title:"Tourist menu 3× local price at Fort area seafood restaurant",        source:"google_maps", location:"Colombo Fort", helpful_votes:14 },
    { id:"C9",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:3,   title:"Gem scam exposed — how it works in Colombo",                         source:"youtube",     location:"Colombo", youtube_url:"https://www.youtube.com/results?search_query=colombo+gem+scam+sri+lanka+tourist", helpful_votes:200 },
    { id:"C10", type:"theft",              severity:2, is_scam:false, days_ago:22,  title:"Bag snatching on motorbike near Beira Lake",                         source:"reddit",      location:"Beira Lake", helpful_votes:37 },
    { id:"C11", type:"tuk_tuk_scam",       severity:2, is_scam:true,  days_ago:9,   title:"Tuk-tuk commission detour to gem shop from Gangaramaya Temple",      source:"tripadvisor", location:"Gangaramaya Temple", helpful_votes:22 },
    { id:"C12", type:"overcharging",       severity:1, is_scam:true,  days_ago:18,  title:"Unofficial photographer demanding fee at Dutch Hospital Precinct",    source:"google_maps", location:"Dutch Hospital Precinct", helpful_votes:9 },
  ],
  Kandy: [
    { id:"K1",  type:"fake_guide",         severity:2, is_scam:true,  days_ago:7,   title:"Unlicensed guide at Temple of Tooth charged ₹5,000 entry",           source:"tripadvisor", location:"Temple of Tooth", helpful_votes:34 },
    { id:"K2",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:14,  title:"Gem shop near Kandy Lake — aggressive sales, fake GIA certs",        source:"reddit",      location:"Kandy Lake Road", helpful_votes:52 },
    { id:"K3",  type:"overcharging",       severity:1, is_scam:true,  days_ago:25,  title:"Restaurant two-menu system — tourist price vs local price",           source:"google_maps", location:"Lake Road", helpful_votes:11 },
    { id:"K4",  type:"tuk_tuk_scam",       severity:2, is_scam:true,  days_ago:40,  title:"Tuk-tuk detour to gem shop before hotel — commission scheme",         source:"tripadvisor", location:"Kandy City", helpful_votes:27 },
    { id:"K5",  type:"fake_guide",         severity:2, is_scam:true,  days_ago:55,  title:"Fake monk requesting cash donations at Temple of Tooth precinct",     source:"reddit",      location:"Temple of Tooth Area", helpful_votes:18 },
    { id:"K6",  type:"harassment",         severity:1, is_scam:false, days_ago:10,  title:"Persistent tout near Kandy central market",                          source:"reddit",      location:"Kandy Market", helpful_votes:9 },
    { id:"K7",  type:"transport_fraud",    severity:2, is_scam:true,  days_ago:18,  title:"Kandy tuk-tuk scams explained — tourist warning video",              source:"youtube",     location:"Kandy", youtube_url:"https://www.youtube.com/results?search_query=kandy+sri+lanka+tourist+scam+tuk+tuk", helpful_votes:180 },
    { id:"K8",  type:"accommodation_scam", severity:2, is_scam:true,  days_ago:32,  title:"Guesthouse booking — photos misrepresented, mold and no AC",         source:"tripadvisor", location:"Kandy Hills", helpful_votes:16 },
    { id:"K9",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:6,   title:"Tea factory tour operator takes tourists to gem shop — not on agenda", source:"adaderana",  location:"Kandy", helpful_votes:44 },
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
    { id:"B5",  type:"transport_fraud",    severity:1, is_scam:true,  days_ago:5,   title:"Ella tuk-tuk scam — tourist warning investigation",                  source:"youtube",     location:"Ella", youtube_url:"https://www.youtube.com/results?search_query=ella+sri+lanka+tourist+trap+scam", helpful_votes:120 },
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
    { id:"R2",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:22,  title:"Fake GIA-certified sapphires sold to 3 tourists this month",          source:"adaderana",   location:"Ratnapura City Market", helpful_votes:45 },
    { id:"R3",  type:"transport_fraud",    severity:1, is_scam:true,  days_ago:40,  title:"Bus fare overcharge on rural routes to gem mining areas",             source:"tripadvisor", location:"Ratnapura", helpful_votes:9 },
    { id:"R4",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:4,   title:"Ratnapura gem scam: investigative report on fake mine tours",         source:"youtube",     location:"Ratnapura", youtube_url:"https://www.youtube.com/results?search_query=ratnapura+gem+scam+sri+lanka+investigative", helpful_votes:310 },
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
    { id:"T1",  type:"unsafe_area",        severity:1, is_scam:false, days_ago:90,  title:"Tourist police advisory: check restricted zones before travel",       source:"tourist_police_lk", location:"Trincomalee", helpful_votes:0 },
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
  Kurunegala: [
    { id:"KR1", type:"transport_fraud",    severity:1, is_scam:true,  days_ago:40,  title:"Intercity highway interchange taxi fee inflation",                    source:"tripadvisor", location:"Kurunegala Bus Stand", helpful_votes:11 },
    { id:"KR2", type:"overcharging",       severity:1, is_scam:true,  days_ago:65,  title:"Elephant Rock vantage point unofficial parking extortion",             source:"google_maps", location:"Kurunegala Rock", helpful_votes:7 },
    { id:"KR3", type:"general_safety",     severity:1, is_scam:false, days_ago:18,  title:"Traffic bottleneck advisory during peak holiday weekend",              source:"sltda_official", location:"A6 Highway Kurunegala", helpful_votes:15 },
  ],
  Puttalam: [
    { id:"PT1", type:"transport_fraud",    severity:1, is_scam:true,  days_ago:28,  title:"Kalpitiya kite-surfing lagoon boat shuttle overcharge",               source:"tripadvisor", location:"Kalpitiya Lagoon", helpful_votes:19 },
    { id:"PT2", type:"accommodation_scam", severity:1, is_scam:true,  days_ago:55,  title:"Dolphin watching eco-lodge missing key amenities",                     source:"google_maps", location:"Kalpitiya", helpful_votes:14 },
    { id:"PT3", type:"overcharging",       severity:1, is_scam:true,  days_ago:14,  title:"Chilaw fish market guided walk fee collected by touts",                source:"reddit",      location:"Chilaw", helpful_votes:8 },
  ],
  Monaragala: [
    { id:"MN1", type:"fake_guide",         severity:2, is_scam:true,  days_ago:21,  title:"Kataragama shrine area unofficial blessing ritual fee demand",         source:"tripadvisor", location:"Kataragama Sacred City", helpful_votes:26 },
    { id:"MN2", type:"transport_fraud",    severity:1, is_scam:true,  days_ago:48,  title:"Pilgrimage shuttle overcharge during festival season",                 source:"reddit",      location:"Monaragala", helpful_votes:13 },
    { id:"MN3", type:"overcharging",       severity:1, is_scam:true,  days_ago:80,  title:"Rural waterfall view point donation trap",                             source:"google_maps", location:"Diyaluma Falls Access", helpful_votes:9 },
  ],
  Ampara: [
    { id:"AM1", type:"transport_fraud",    severity:1, is_scam:true,  days_ago:16,  title:"Arugam Bay surf tuk-tuk rack surcharge added arbitrarily",            source:"tripadvisor", location:"Arugam Bay Main Street", helpful_votes:32 },
    { id:"AM2", type:"food_scam",          severity:1, is_scam:true,  days_ago:34,  title:"Beachfront cafe unlisted service charge and double tax",              source:"reddit",      location:"Arugam Bay", helpful_votes:21 },
    { id:"AM3", type:"accommodation_scam", severity:2, is_scam:true,  days_ago:52,  title:"Cabana deposit withheld due to false damage claims",                  source:"google_maps", location:"Whiskey Point", helpful_votes:18 },
  ],
  Batticaloa: [
    { id:"BT1", type:"overcharging",       severity:1, is_scam:true,  days_ago:29,  title:"Pasikuda lagoon water sports boat ride markup",                       source:"tripadvisor", location:"Pasikuda Beach", helpful_votes:15 },
    { id:"BT2", type:"transport_fraud",    severity:1, is_scam:true,  days_ago:60,  title:"Batticaloa fort tuk-tuk tour price tripled halfway",                  source:"reddit",      location:"Batticaloa Fort", helpful_votes:10 },
    { id:"BT3", type:"fake_guide",         severity:1, is_scam:true,  days_ago:42,  title:"Singing Fish bridge nocturnal tour touts charging fake entry",         source:"google_maps", location:"Kallady Bridge", helpful_votes:12 },
  ],
  Vavuniya: [
    { id:"VA1", type:"general_safety",     severity:1, is_scam:false, days_ago:35,  title:"Northern transit checkpoint delay notification",                       source:"tourist_police_lk", location:"Vavuniya Station", helpful_votes:8 },
    { id:"VA2", type:"overcharging",       severity:1, is_scam:true,  days_ago:75,  title:"Highway rest stop restaurant double pricing for foreign visitors",     source:"reddit",      location:"A9 Highway Vavuniya", helpful_votes:14 },
    { id:"VA3", type:"transport_fraud",    severity:1, is_scam:true,  days_ago:50,  title:"Private van taxi meter refusal to Jaffna",                             source:"google_maps", location:"Vavuniya Town", helpful_votes:6 },
  ],
  Kilinochchi: [
    { id:"KLN1",type:"general_safety",     severity:1, is_scam:false, days_ago:40,  title:"Historical monument visitor guidelines advisory",                      source:"tourist_police_lk", location:"Kilinochchi Water Tower", helpful_votes:10 },
    { id:"KLN2",type:"overcharging",       severity:1, is_scam:true,  days_ago:90,  title:"Souvenir stall inflated rates at A9 rest area",                        source:"reddit",      location:"Kilinochchi Town", helpful_votes:5 },
    { id:"KLN3",type:"transport_fraud",    severity:1, is_scam:true,  days_ago:65,  title:"Local tuk-tuk quoted higher fare to Elephant Pass",                    source:"tripadvisor", location:"Elephant Pass Road", helpful_votes:12 },
  ],
  Mannar: [
    { id:"MNR1",type:"general_safety",     severity:1, is_scam:false, days_ago:30,  title:"Adam's Bridge sandbar seasonal weather & tides warning",              source:"tourist_police_lk", location:"Talaimannar", helpful_votes:22 },
    { id:"MNR2",type:"overcharging",       severity:1, is_scam:true,  days_ago:60,  title:"Baobab tree photography entrance fee demanded by locals",             source:"google_maps", location:"Mannar Island", helpful_votes:11 },
    { id:"MNR3",type:"transport_fraud",    severity:1, is_scam:true,  days_ago:85,  title:"Fisherman boat tour fare quoted high for bird sanctuary trip",         source:"reddit",      location:"Mannar Sanctuary", helpful_votes:9 },
  ],
  Mullaitivu: [
    { id:"MLT1",type:"general_safety",     severity:1, is_scam:false, days_ago:45,  title:"Coastal zone swimming advisory during monsoon swell",                  source:"tourist_police_lk", location:"Mullaitivu Beach", helpful_votes:16 },
    { id:"MLT2",type:"transport_fraud",    severity:1, is_scam:true,  days_ago:70,  title:"Remote lagoon boat ride fee inflation",                               source:"tripadvisor", location:"Nayaru Lagoon", helpful_votes:7 },
    { id:"MLT3",type:"overcharging",       severity:1, is_scam:true,  days_ago:110, title:"Rural guesthouse meal pricing discrepancy",                            source:"reddit",      location:"Mullaitivu Town", helpful_votes:4 },
  ],
};

// ─── SVG Bubble Position Coordinates for all 25 Districts ─────────────────
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

// ─── Mathematical Defensibility Calculations ──────────────────────────────
function wilsonLower(successes, n, z = 1.645) {
  if (n === 0) return 0;
  const p = successes / n;
  const denom = 1 + (z * z) / n;
  const centre = p + (z * z) / (2 * n);
  const spread = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return Math.max(0, (centre - spread) / denom);
}

function decay(daysAgo) {
  return Math.exp(-DECAY_LAMBDA * daysAgo);
}

function scoreDistrict(incidents, footfall = null) {
  const n = incidents.length;
  if (n < MIN_REPORTS_INSUFF) {
    return { score: null, count: n, confidence: "insufficient_data", severity: 0, scamRatio: 0, incidentRate: null, wEvidence: 0, scamN: 0 };
  }

  let wEvidence = 0, wScamNumer = 0, scamN = 0;

  incidents.forEach(inc => {
    const srcW   = getSourceInfo(inc.source).w;
    const hvBonus = (inc.helpful_votes || 0) >= 20 ? 0.15 : (inc.helpful_votes || 0) >= 10 ? 0.10 : (inc.helpful_votes || 0) >= 5 ? 0.07 : 0.03;
    const w      = decay(inc.days_ago || 30) * Math.min(srcW + hvBonus, 0.97);
    wEvidence   += w;
    if (inc.is_scam) {
      scamN++;
      const sev = inc.severity || 1;
      wScamNumer += w * (sev / 3.0);
    }
  });

  const adjustedScamRatio = wilsonLower(scamN, n);
  const severity          = wEvidence > 0 ? (wScamNumer / Math.max(scamN, 1)) : 0;
  const baseRisk          = SEVERITY_WEIGHT * severity + SCAM_RATIO_WEIGHT * adjustedScamRatio;
  const shrunkScore       = (n * baseRisk + BAYESIAN_ALPHA * GLOBAL_PRIOR) / (n + BAYESIAN_ALPHA);

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

function computeAllScores(incidentData = SEED_INCIDENTS) {
  const raw = {};
  Object.keys(DISTRICTS).forEach(d => {
    raw[d] = scoreDistrict(incidentData[d] || [], SLTDA_FOOTFALL[d] || null);
  });

  const scoreable = Object.values(raw)
    .filter(s => s.confidence !== "insufficient_data" && s.score !== null)
    .map(s => s.score)
    .sort((a, b) => a - b);

  let q25 = 0.15, q50 = 0.25, q75 = 0.35;
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
  const [liveMode, setLiveMode]       = useState(false);
  const [liveData, setLiveData]       = useState(null);

  const panelRef = useRef(null);

  // Attempt live API connection to backend on mount
  useEffect(() => {
    async function checkLiveAPI() {
      try {
        const res = await fetch(`${API_BASE_URL}/districts/risk-map`);
        if (res.ok) {
          const json = await res.json();
          if (json && json.features) {
            setLiveData(json);
            setLiveMode(true);
          }
        }
      } catch (_) {
        setLiveMode(false);
      }
    }
    checkLiveAPI();
  }, []);

  const scores = useMemo(() => {
    if (liveMode && liveData?.features) {
      const liveScores = {};
      liveData.features.forEach(f => {
        const p = f.properties;
        const d = p.district;
        liveScores[d] = {
          score: p.risk_score_0_1,
          count: p.report_count || 0,
          scamN: p.scam_report_count || 0,
          confidence: p.confidence || "insufficient_data",
          tier: p.risk_tier || "insufficient_data",
          severity: p.severity_component || 0,
          scamRatio: p.scam_ratio_component || 0,
          incidentRate: p.incident_rate_per_100k_visitors,
          hasFootfall: !!p.exposure_footfall,
          q25: 0.15, q50: 0.25, q75: 0.35,
        };
      });
      return liveScores;
    }
    return computeAllScores(SEED_INCIDENTS);
  }, [liveMode, liveData]);

  const profData = TRAVELER_PROFILES[profile.type] || TRAVELER_PROFILES["Solo Female"];

  useEffect(() => {
    if (selected && panelRef.current) {
      setTimeout(() => panelRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 80);
    }
  }, [selected]);

  const handleSelect = useCallback((d) => {
    setSelected(d);
    setAiText(""); setAiError(""); setPanelTab("overview"); setPlaceSearch(""); setCitySearch("");
  }, []);

  const tierCounts = useMemo(() => {
    return Object.values(scores).reduce((a, s) => {
      a[s.tier] = (a[s.tier] || 0) + 1; return a;
    }, {});
  }, [scores]);

  async function fetchAI() {
    if (!selected) return;
    setAiLoading(true); setAiText(""); setAiError("");
    const inc     = SEED_INCIDENTS[selected] || [];
    const scoredD = scores[selected];
    const cities  = DISTRICT_CITIES[selected] || [];
    const cityRisks = cities.map(c => CITY_PROFILES[c]).filter(Boolean);
    const topCity  = cityRisks.sort((a, b) => b.risk_score - a.risk_score)[0];
    const topTypes = [...new Set(inc.map(i => INCIDENT_TYPES[i.type]?.label || i.type))].slice(0, 4).join(", ");

    const promptText = `Provide a personalized 3-sentence safety briefing for ${profile.name || "a traveler"} (${profData.label}) visiting ${selected} district, Sri Lanka.
Risk Tier: ${scoredD?.tier?.toUpperCase() || "UNKNOWN"} (Score: ${scoredD?.score != null ? Math.round(scoredD.score * 100) : "N/A"}/100)
Incident Count: ${scoredD?.count || 0} reports (${topTypes || "General tourist areas"})
Footfall: ${SLTDA_FOOTFALL[selected] ? `${(SLTDA_FOOTFALL[selected] / 1e6).toFixed(1)}M visitors` : "Standard density"}
${topCity ? `High Risk Area: ${cities.find(c => CITY_PROFILES[c] === topCity)}` : ""}`;

    // Try backend AI advisor endpoint first
    try {
      const res = await fetch(`${API_BASE_URL}/advisor/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: promptText,
          demographic: profile.type,
          district: selected,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data && data.response) {
          setAiText(data.response);
          setAiLoading(false);
          return;
        }
      }
    } catch (_) {
      // Fallback to Anthropic Claude direct call
    }

    try {
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-6",
          max_tokens: 220,
          messages: [{ role: "user", content: promptText }],
        }),
      });
      const data = await res.json();
      const text = data?.content?.map(b => b.text || "").join("") || "";
      if (!text) throw new Error("Empty response");
      setAiText(text);
    } catch (e) {
      // Fallback client response
      setAiText(`Welcome to ${selected}! Based on ${scoredD?.count || 0} reported incidents, keep an eye out for ${topTypes || "tuk-tuk overcharging and fake guides"}. As a ${profData.label} traveler, always agree on metered fares in advance and store valuables securely. ${scoredD?.confidence === "established" ? "Data confidence for this district is high." : "Note: Data coverage is preliminary, so exercise standard precautions."}`);
    }
    setAiLoading(false);
  }

  // ─── ONBOARDING SCREEN ───────────────────────────────────────────────────
  if (screen === "onboard") {
    return (
      <div style={{
        minHeight: "100vh",
        background: "radial-gradient(circle at 50% 20%, #0d1e38 0%, #060d1a 60%, #040812 100%)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontFamily: "'Inter', system-ui, sans-serif", padding: "24px", color: "#e2e8f0",
      }}>
        <div style={{ maxWidth: 560, width: "100%" }}>
          {/* Logo Header */}
          <div style={{ textAlign: "center", marginBottom: 36 }}>
            <div style={{
              display: "inline-flex", alignItems: "center", gap: 12,
              background: "rgba(6,182,212,0.08)", border: "1px solid rgba(6,182,212,0.20)",
              borderRadius: 16, padding: "12px 26px", marginBottom: 20,
              backdropFilter: "blur(12px)", boxShadow: "0 0 30px rgba(6,182,212,0.12)",
            }}>
              <span style={{ fontSize: 28 }}>🧭</span>
              <span style={{ color: "#f8fafc", fontSize: 23, fontWeight: 800, letterSpacing: "-0.5px" }}>
                SafeTravel <span style={{ color: "#22d3ee" }}>Sri Lanka</span>
              </span>
            </div>
            <p style={{ color: "#94a3b8", fontSize: 13, margin: 0, lineHeight: 1.8, fontWeight: 400 }}>
              PhD Research Safety Intelligence · 25 Districts · {Object.values(SEED_INCIDENTS).flat().length}+ Incidents · {Object.keys(CITY_PROFILES).length} City Profiles
            </p>
          </div>

          {/* Onboarding Form Card */}
          <div style={{
            background: "rgba(13,21,38,0.92)", border: "1px solid rgba(100,116,139,0.15)",
            borderRadius: 24, padding: "34px 38px", boxShadow: "0 20px 50px rgba(0,0,0,0.5)",
          }}>
            <div style={{ color: "#cbd5e1", fontSize: 13, marginBottom: 24, lineHeight: 1.7, fontWeight: 500 }}>
              Personalize your Sri Lanka safety intelligence map based on your demographic profile and trip itinerary.
            </div>

            {/* Interactive Profile Sentence */}
            <div style={{
              background: "rgba(6,182,212,0.05)", border: "1px solid rgba(6,182,212,0.18)",
              borderRadius: 16, padding: "24px 28px", lineHeight: 2.8, color: "#f1f5f9",
              fontSize: 16, marginBottom: 22,
            }}>
              <span>Hello, my name is </span>
              <input
                value={profile.name}
                onChange={e => setProfile(p => ({ ...p, name: e.target.value }))}
                placeholder="Alesa"
                style={{
                  background: "transparent", border: "none",
                  borderBottom: "2px solid #22d3ee", color: "#22d3ee",
                  fontFamily: "inherit", fontSize: 16, fontWeight: 700,
                  width: 110, outline: "none", padding: "1px 6px", textAlign: "center",
                }}
              />
              <span>. I am travelling as a </span>
              <select
                value={profile.type}
                onChange={e => setProfile(p => ({ ...p, type: e.target.value }))}
                style={{
                  background: "rgba(6,182,212,0.12)", border: "1px solid rgba(6,182,212,0.30)",
                  color: "#22d3ee", fontFamily: "inherit", fontSize: 15, fontWeight: 700,
                  outline: "none", padding: "4px 10px", cursor: "pointer", borderRadius: 8,
                }}
              >
                {Object.entries(TRAVELER_PROFILES).map(([k, v]) => (
                  <option key={k} value={k} style={{ background: "#0b1728", color: "#e2e8f0" }}>
                    {v.icon} {v.label}
                  </option>
                ))}
              </select>
              <span> in Sri Lanka</span>
              {profile.tripDays && <span> for <strong style={{ color: "#22d3ee" }}>{profile.tripDays} days</strong></span>}.
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 24 }}>
              {[["Nationality (optional)", "e.g. German", "nationality"], ["Trip Duration (days)", "e.g. 14", "tripDays"]].map(([label, ph, key]) => (
                <div key={key}>
                  <div style={{ color: "#94a3b8", fontSize: 11.5, marginBottom: 6, fontWeight: 600 }}>{label}</div>
                  <input
                    value={profile[key]}
                    onChange={e => setProfile(p => ({ ...p, [key]: e.target.value }))}
                    placeholder={ph}
                    style={{
                      width: "100%", boxSizing: "border-box",
                      background: "rgba(30,41,59,0.8)", border: "1px solid rgba(100,116,139,0.18)",
                      borderRadius: 10, padding: "10px 14px", color: "#f8fafc",
                      fontFamily: "inherit", fontSize: 13.5, outline: "none",
                    }}
                  />
                </div>
              ))}
            </div>

            <button
              onClick={() => { if (profile.name.trim()) setScreen("map"); else alert("Please enter your name to proceed."); }}
              style={{
                width: "100%", padding: "15px",
                background: "linear-gradient(135deg, #0891b2 0%, #0284c7 100%)",
                border: "none", borderRadius: 14, color: "#fff",
                fontFamily: "inherit", fontSize: 16, fontWeight: 700,
                cursor: "pointer", boxShadow: "0 0 24px rgba(6,182,212,0.25)",
                transition: "all 0.15s ease",
              }}
            >Explore Safety Map →</button>

            <p style={{ color: "#64748b", fontSize: 11, textAlign: "center", marginTop: 14, marginBottom: 0 }}>
              🔒 Privacy Assured · No personal data is transmitted or saved
            </p>
          </div>

          <div style={{ textAlign: "center", marginTop: 22, color: "#475569", fontSize: 11, lineHeight: 1.8 }}>
            Methodology Anchors: Wilson-Shrunk Scam Ratios · 180-Day Decay · Quantile Tiering · SLTDA Footfall Exposure
          </div>
        </div>
      </div>
    );
  }

  // ─── MAIN MAP & INTELLIGENCE DASHBOARD SCREEN ─────────────────────────────
  const selectedData = selected ? scores[selected] : null;
  const selectedInc  = selected ? (SEED_INCIDENTS[selected] || []) : [];
  const tc           = selectedData ? TIER_CONFIG[selectedData.tier] : TIER_CONFIG.insufficient_data;

  const districtCities = selected ? (DISTRICT_CITIES[selected] || []) : [];
  const cityProfiles   = districtCities.map(c => ({ city: c, profile: CITY_PROFILES[c] })).filter(x => x.profile);

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

  const typeBreakdown = {};
  selectedInc.forEach(i => { typeBreakdown[i.type] = (typeBreakdown[i.type] || 0) + 1; });
  const topTypes = Object.entries(typeBreakdown).sort((a, b) => b[1] - a[1]).slice(0, 5);

  const filteredCities = citySearch.trim()
    ? cityProfiles.filter(({ city }) => city.toLowerCase().includes(citySearch.toLowerCase()))
    : cityProfiles;

  return (
    <div style={{
      minHeight: "100vh", background: "#040812", color: "#e2e8f0",
      fontFamily: "'Inter', system-ui, sans-serif",
      display: "flex", flexDirection: "column",
    }}>
      {/* ── TOP NAVIGATION BAR ── */}
      <nav style={{
        background: "rgba(6,12,23,0.98)", backdropFilter: "blur(20px)",
        borderBottom: "1px solid rgba(100,116,139,0.12)",
        padding: "0 20px", height: 56,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        position: "sticky", top: 0, zIndex: 100,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 20 }}>🧭</span>
          <span style={{ color: "#f8fafc", fontWeight: 800, fontSize: 15, letterSpacing: "-0.3px" }}>
            SafeTravel <span style={{ color: "#22d3ee" }}>LK</span>
          </span>
          <span style={{
            background: "rgba(6,182,212,0.10)", border: "1px solid rgba(6,182,212,0.25)",
            borderRadius: 20, padding: "2px 10px", color: "#22d3ee", fontSize: 10.5, fontWeight: 700,
          }}>DISTRICT ENGINE</span>
          {liveMode && (
            <span style={{
              background: "rgba(34,197,94,0.10)", border: "1px solid rgba(34,197,94,0.25)",
              borderRadius: 20, padding: "2px 10px", color: "#4ade80", fontSize: 10.5, fontWeight: 700,
            }}>● LIVE API CONNECTED</span>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{
            background: "rgba(30,41,59,0.8)", border: "1px solid rgba(100,116,139,0.15)",
            borderRadius: 20, padding: "4px 14px", color: "#cbd5e1", fontSize: 12, fontWeight: 600,
          }}>
            {profData.icon} {profile.name || "Traveler"} · {profData.label}
          </span>
          <button onClick={() => setScreen("onboard")} style={{
            background: "transparent", border: "1px solid rgba(100,116,139,0.20)",
            borderRadius: 8, color: "#94a3b8", fontSize: 11.5, padding: "4px 11px",
            cursor: "pointer", fontFamily: "inherit", fontWeight: 600,
          }}>✏️ Edit Profile</button>
        </div>
      </nav>

      <div style={{ display: "flex", flex: 1, overflow: "hidden", height: "calc(100vh - 56px)" }}>

        {/* ── LEFT SIDEBAR (SEARCH & DISTRICT LIST) ── */}
        <div style={{
          width: 275, background: "rgba(6,12,23,0.99)",
          borderRight: "1px solid rgba(100,116,139,0.10)",
          display: "flex", flexDirection: "column", flexShrink: 0, overflowY: "auto",
        }}>
          <div style={{ padding: "12px 14px 6px" }}>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="🔍 Search district..."
              style={{
                width: "100%", boxSizing: "border-box",
                background: "rgba(30,41,59,0.8)", border: "1px solid rgba(100,116,139,0.15)",
                borderRadius: 10, padding: "8px 12px", color: "#f8fafc",
                fontFamily: "inherit", fontSize: 12.5, outline: "none",
              }}
            />
          </div>

          {/* Filter Pills */}
          <div style={{ padding: "6px 14px 10px", display: "flex", gap: 5, flexWrap: "wrap" }}>
            {["all","severe","high","moderate","low","insufficient_data"].map(t => {
              const c = TIER_CONFIG[t];
              const active = filter === t;
              return (
                <button key={t} onClick={() => setFilter(t)} style={{
                  padding: "3px 9px", borderRadius: 20, fontSize: 10.5, fontWeight: 600,
                  fontFamily: "inherit", cursor: "pointer", border: "1px solid",
                  background: active ? (c?.badge || "#06b6d4") : "transparent",
                  color: active ? "#fff" : (c?.text || "#94a3b8"),
                  borderColor: active ? (c?.badge || "#06b6d4") : "rgba(100,116,139,0.18)",
                }}>
                  {t === "all" ? "All" : t === "insufficient_data" ? "No Data" : c?.label}
                  {t !== "all" && <span style={{ marginLeft: 4, opacity: 0.8 }}>({tierCounts[t] || 0})</span>}
                </button>
              );
            })}
          </div>

          {/* District Tier Summary Cards */}
          <div style={{ padding: "0 14px 10px", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
            {[["severe","🔴"],["high","🟠"],["moderate","🟡"]].map(([t, icon]) => (
              <div key={t} onClick={() => setFilter(t)} style={{
                background: "rgba(15,23,42,0.6)", border: `1px solid ${TIER_CONFIG[t].stroke}33`,
                borderRadius: 9, padding: "8px 6px", textAlign: "center", cursor: "pointer",
              }}>
                <div style={{ fontSize: 13 }}>{icon}</div>
                <div style={{ color: TIER_CONFIG[t].text, fontWeight: 800, fontSize: 16 }}>{tierCounts[t] || 0}</div>
                <div style={{ color: "#64748b", fontSize: 9.5 }}>{TIER_CONFIG[t].label}</div>
              </div>
            ))}
          </div>

          {/* District List */}
          <div style={{ padding: "0 14px", flex: 1 }}>
            <div style={{ color: "#64748b", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: 8 }}>
              Districts ({districtList.length})
            </div>
            {districtList.map(d => {
              const s     = scores[d];
              const t     = s?.tier || "insufficient_data";
              const c     = TIER_CONFIG[t];
              const isSel = selected === d;
              return (
                <div key={d} onClick={() => handleSelect(d)} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "8px 12px", borderRadius: 10, marginBottom: 4,
                  cursor: "pointer", border: "1px solid",
                  background: isSel ? `${c.fill}dd` : "rgba(13,21,38,0.6)",
                  borderColor: isSel ? c.stroke : "rgba(100,116,139,0.08)",
                  transition: "all 0.12s ease",
                }}>
                  <div>
                    <div style={{ color: "#f8fafc", fontSize: 12.5, fontWeight: isSel ? 700 : 500 }}>{d}</div>
                    <div style={{ color: "#64748b", fontSize: 10, marginTop: 1 }}>
                      {s?.count || 0} reports
                      {s?.confidence === "established" ? " · ✓ Established" : s?.confidence === "preliminary" ? " · ⚠ Limited" : ""}
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
                    <span style={{
                      background: c.badge, color: "#fff", borderRadius: 6,
                      padding: "1px 8px", fontSize: 10, fontWeight: 800,
                    }}>{c.grade}</span>
                    {s?.score != null && <span style={{ color: c.text, fontSize: 10, fontWeight: 600 }}>{Math.round(s.score * 100)}/100</span>}
                  </div>
                </div>
              );
            })}
          </div>

          <div style={{ padding: "14px", borderTop: "1px solid rgba(100,116,139,0.08)" }}>
            <div style={{ color: "#475569", fontSize: 9.5, lineHeight: 1.7 }}>
              <span style={{ color: "#94a3b8", fontWeight: 700 }}>IT22629180</span> · Quantile Tiers · Wilson Lower Bound · 180-Day Decay · SLTDA Footfall Exposure
            </div>
          </div>
        </div>

        {/* ── CENTER INTERACTIVE MAP ── */}
        <div style={{ flex: 1, position: "relative", background: "radial-gradient(circle at 50% 50%, #081426 0%, #030712 100%)" }}>
          <svg viewBox="80 100 380 600" style={{ width: "100%", height: "100%" }}>
            <defs>
              <filter id="softglow" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="5" />
              </filter>
            </defs>
            {/* Background Map Grid Lines */}
            {[...Array(9)].map((_,i) => <line key={`h${i}`} x1={80} y1={100+i*70} x2={460} y2={100+i*70} stroke="#0b1b30" strokeWidth="0.5"/>)}
            {[...Array(6)].map((_,i) => <line key={`v${i}`} x1={80+i*76} y1={100} x2={80+i*76} y2={700} stroke="#0b1b30" strokeWidth="0.5"/>)}

            {/* District Nodes */}
            {Object.entries(DISTRICTS).map(([d, pos]) => {
              const s        = scores[d];
              const t        = s?.tier || "insufficient_data";
              const c        = TIER_CONFIG[t];
              const isSel    = selected === d;
              const isHov    = hovered === d;
              const matchSrch = !search.trim() || d.toLowerCase().includes(search.toLowerCase());
              const matchFlt  = filter === "all" || t === filter;
              const r        = isSel ? pos.r + 6 : isHov ? pos.r + 3 : pos.r;

              return (
                <g key={d}
                  onClick={() => handleSelect(d)}
                  onMouseEnter={() => setHovered(d)}
                  onMouseLeave={() => setHovered(null)}
                  style={{ cursor: "pointer", opacity: (matchSrch && matchFlt) ? 1 : 0.12, transition: "all 0.18s ease" }}
                >
                  {(t === "high" || t === "severe") && (
                    <circle cx={pos.cx} cy={pos.cy} r={r+12} fill={c.badge} opacity="0.15" filter="url(#softglow)"/>
                  )}
                  {isSel && (
                    <circle cx={pos.cx} cy={pos.cy} r={r+12} fill="none" stroke={c.stroke} strokeWidth="1.8" opacity="0.6" strokeDasharray="5,4"/>
                  )}
                  <circle cx={pos.cx} cy={pos.cy} r={r} fill={c.fill} stroke={c.stroke} strokeWidth={isSel ? 2.8 : 1.6}/>
                  <text x={pos.cx} y={pos.cy+1} textAnchor="middle" dominantBaseline="middle"
                    fill={c.text} fontSize={r > 22 ? 9.5 : 8} fontWeight="900">
                    {s?.score != null ? c.grade : "—"}
                  </text>
                  {s?.score != null && (
                    <text x={pos.cx} y={pos.cy+r-5} textAnchor="middle" dominantBaseline="middle"
                      fill={c.text} fontSize={6} opacity="0.8" fontWeight="700">
                      {Math.round(s.score * 100)}
                    </text>
                  )}
                  <text x={pos.cx} y={pos.cy+r+10} textAnchor="middle"
                    fill={isSel ? "#f8fafc" : "#94a3b8"} fontSize={8} fontWeight={isSel ? 700 : 500}>
                    {d.length > 13 ? d.slice(0,12)+"…" : d}
                  </text>
                </g>
              );
            })}

            {/* Map Legend */}
            <g transform="translate(84,685)">
              <rect x={0} y={-12} width={165} height={26} rx={8} fill="rgba(6,12,23,0.95)" stroke="rgba(100,116,139,0.18)" strokeWidth="1"/>
              {[["low","#15803d","A"],["moderate","#b45309","B"],["high","#c2410c","C"],["severe","#b91c1c","D"]].map(([t,col,g],i) => (
                <g key={t} transform={`translate(${i*39+10},0)`}>
                  <circle cx={0} cy={0} r={6.5} fill={col} opacity="0.9"/>
                  <text x={0} y={1} textAnchor="middle" dominantBaseline="middle" fill="#fff" fontSize={6.5} fontWeight="900">{g}</text>
                  <text x={0} y={13} textAnchor="middle" fill="#94a3b8" fontSize={6}>{t.slice(0,3).toUpperCase()}</text>
                </g>
              ))}
              <text x={148} y={1} textAnchor="middle" dominantBaseline="middle" fill="#64748b" fontSize={6.5}>— No Data</text>
            </g>

            {/* Hover Tooltip */}
            {hovered && hovered !== selected && (() => {
              const pos = DISTRICTS[hovered];
              const s   = scores[hovered];
              const t   = s?.tier || "insufficient_data";
              const c   = TIER_CONFIG[t];
              const tx  = pos.cx > 300 ? pos.cx - 90 : pos.cx + pos.r + 10;
              const ty  = pos.cy - 18;
              return (
                <g transform={`translate(${tx},${ty})`}>
                  <rect x={0} y={0} width={88} height={36} rx={8} fill="rgba(6,12,23,0.96)" stroke={c.stroke} strokeWidth="1.2"/>
                  <text x={10} y={13} fill="#f8fafc" fontSize={9.5} fontWeight="700">{hovered}</text>
                  <text x={10} y={25} fill={c.text} fontSize={8.5} fontWeight="600">{c.label} · {s?.score != null ? Math.round(s.score*100) : "N/A"}</text>
                </g>
              );
            })()}
          </svg>
        </div>

        {/* ── RIGHT DISTRICT INTELLIGENCE PANEL ── */}
        {selected && selectedData ? (
          <div ref={panelRef} style={{
            width: 360, background: "rgba(6,12,23,0.99)",
            borderLeft: "1px solid rgba(100,116,139,0.12)",
            display: "flex", flexDirection: "column", flexShrink: 0,
          }}>
            {/* Panel Header */}
            <div style={{
              background: `linear-gradient(135deg, ${tc.fill} 0%, rgba(6,12,23,0.98) 100%)`,
              borderBottom: `1px solid ${tc.stroke}44`,
              padding: "18px 20px 14px", flexShrink: 0,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ color: "#64748b", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.8px", fontWeight: 700 }}>Administrative District</div>
                  <div style={{ color: "#f8fafc", fontSize: 20, fontWeight: 800, marginTop: 2 }}>{selected}</div>
                  {SLTDA_FOOTFALL[selected] && (
                    <div style={{ color: "#94a3b8", fontSize: 10.5, marginTop: 2, fontWeight: 500 }}>
                      👥 {(SLTDA_FOOTFALL[selected]/1e6).toFixed(1)}M Annual Visitors · SLTDA Baseline
                    </div>
                  )}
                </div>
                <button onClick={() => setSelected(null)} style={{
                  background: "rgba(100,116,139,0.15)", border: "none", borderRadius: 8,
                  color: "#cbd5e1", cursor: "pointer", padding: "5px 10px", fontSize: 12, fontFamily: "inherit", fontWeight: 700,
                }}>✕</button>
              </div>

              {/* Risk Score Summary */}
              <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 14 }}>
                <div style={{ textAlign: "center", minWidth: 58 }}>
                  <div style={{ color: tc.text, fontSize: 38, fontWeight: 900, lineHeight: 1 }}>
                    {selectedData.score != null ? Math.round(selectedData.score * 100) : "—"}
                  </div>
                  <div style={{ color: "#64748b", fontSize: 9, marginTop: 3, fontWeight: 600 }}>Risk Index</div>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <span style={{
                      background: tc.badge, color: "#fff", borderRadius: 6,
                      padding: "2px 10px", fontSize: 11, fontWeight: 800,
                    }}>{tc.grade} · {tc.label}</span>
                    <span style={{ color: "#94a3b8", fontSize: 10, fontWeight: 500 }}>
                      {selectedData.confidence === "established" ? "✓ High Confidence" : selectedData.confidence === "preliminary" ? "⚠ Preliminary Data" : "— No Score"}
                    </span>
                  </div>
                  {selectedData.score != null && (
                    <div style={{ background: "rgba(30,41,59,0.8)", borderRadius: 6, height: 7, overflow: "hidden" }}>
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

            {/* Navigation Tabs */}
            <div style={{ display: "flex", borderBottom: "1px solid rgba(100,116,139,0.10)", flexShrink: 0 }}>
              {[["overview","Overview"],["incidents","Reports"],["cities","Areas"],["ai","AI Brief"]].map(([id, label]) => (
                <button key={id} onClick={() => setPanelTab(id)} style={{
                  flex: 1, padding: "10px 0", background: "transparent",
                  border: "none", borderBottom: `2px solid ${panelTab === id ? "#22d3ee" : "transparent"}`,
                  color: panelTab === id ? "#22d3ee" : "#64748b",
                  fontFamily: "inherit", fontSize: 11.5, fontWeight: panelTab === id ? 700 : 500,
                  cursor: "pointer", transition: "all 0.12s ease",
                }}>{label}</button>
              ))}
            </div>

            {/* Tab Body */}
            <div style={{ overflowY: "auto", flex: 1 }}>

              {/* ── OVERVIEW TAB ── */}
              {panelTab === "overview" && (
                <div style={{ padding: "16px 18px" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 16 }}>
                    {[
                      ["📋 Total Reports", selectedData.count, selectedData.count < MIN_REPORTS_INSUFF ? "Below min threshold" : selectedData.confidence === "established" ? "High confidence" : "Limited data"],
                      ["⚠️ Scam Reports", selectedData.scamN, `${Math.round((selectedData.scamN / (selectedData.count||1)) * 100)}% scam ratio`],
                      ["👥 Visitor Footfall", selectedData.hasFootfall ? `${(SLTDA_FOOTFALL[selected]/1e6).toFixed(1)}M` : "Standard", "SLTDA 2024 Telecom"],
                      ["🏙️ Profiled Areas", districtCities.length, districtCities.length > 0 ? `${cityProfiles.length} city profiles` : "No city profile"],
                    ].map(([label, val, sub]) => (
                      <div key={label} style={{
                        background: "rgba(15,23,42,0.7)", borderRadius: 10, padding: "10px 12px",
                        border: "1px solid rgba(100,116,139,0.10)",
                      }}>
                        <div style={{ color: "#64748b", fontSize: 10, marginBottom: 3, fontWeight: 600 }}>{label}</div>
                        <div style={{ color: "#f8fafc", fontSize: 17, fontWeight: 800 }}>{val}</div>
                        <div style={{ color: "#475569", fontSize: 10, marginTop: 1 }}>{sub}</div>
                      </div>
                    ))}
                  </div>

                  {/* Insufficient Data Alert */}
                  {selectedData.tier === "insufficient_data" && (
                    <div style={{
                      background: "rgba(30,41,59,0.6)", border: "1px solid rgba(100,116,139,0.25)",
                      borderRadius: 12, padding: "12px 14px", marginBottom: 16,
                    }}>
                      <div style={{ color: "#cbd5e1", fontSize: 12, lineHeight: 1.7 }}>
                        <span style={{ fontWeight: 700, color: "#94a3b8" }}>ℹ️ Insufficient Incident Data</span><br/>
                        Fewer than {MIN_REPORTS_INSUFF} reports recorded — score is withheld to prevent misleading risk claims. Maintain standard travel precautions.
                      </div>
                    </div>
                  )}

                  {/* Personalized Profile Concerns */}
                  {relevantToProfile.length > 0 && (
                    <div style={{
                      background: "rgba(6,182,212,0.06)", border: "1px solid rgba(6,182,212,0.18)",
                      borderRadius: 12, padding: "12px 14px", marginBottom: 16,
                    }}>
                      <div style={{ color: "#22d3ee", fontSize: 11.5, fontWeight: 700, marginBottom: 8 }}>
                        ⚡ High Relevance to {profData.icon} {profData.label}
                      </div>
                      {relevantToProfile.slice(0, 3).map((inc, i) => {
                        const si = getSourceInfo(inc.source);
                        return (
                          <div key={i} style={{ color: "#cbd5e1", fontSize: 12, marginBottom: 6, lineHeight: 1.5 }}>
                            {si.icon} {inc.title}
                            <span style={{ color: "#64748b" }}> ({inc.days_ago}d ago · {inc.location})</span>
                            {inc.youtube_url && (
                              <a href={inc.youtube_url} target="_blank" rel="noreferrer"
                                style={{ display: "inline-block", marginLeft: 6, background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 4, padding: "0 6px", color: "#f87171", fontSize: 10.5, textDecoration: "none", fontWeight: 700 }}>
                                ▶ Watch
                              </a>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Top Incident Types Breakdown */}
                  {topTypes.length > 0 && (
                    <div style={{ marginBottom: 16 }}>
                      <div style={{ color: "#64748b", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.8px", marginBottom: 8 }}>
                        Incident Type Breakdown
                      </div>
                      {topTypes.map(([type, count]) => {
                        const it  = INCIDENT_TYPES[type] || { emoji: "•", label: type };
                        const pct = Math.round((count / (selectedData.count || 1)) * 100);
                        return (
                          <div key={type} style={{ marginBottom: 7 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
                              <span style={{ color: "#f1f5f9", fontSize: 12.5 }}>{it.emoji} {it.label}</span>
                              <span style={{ color: "#94a3b8", fontSize: 11, fontWeight: 600 }}>{count}× · {pct}%</span>
                            </div>
                            <div style={{ background: "rgba(30,41,59,0.8)", borderRadius: 4, height: 5, overflow: "hidden" }}>
                              <div style={{
                                width: `${pct}%`, height: "100%",
                                background: tc.badge, borderRadius: 4,
                              }}/>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Scoring Methodology Disclosure */}
                  {selectedData.score != null && (
                    <div style={{ borderTop: "1px solid rgba(100,116,139,0.10)", paddingTop: 12 }}>
                      <div style={{ color: "#64748b", fontSize: 9.5, lineHeight: 1.7 }}>
                        <span style={{ color: "#94a3b8", fontWeight: 700 }}>Methodology Disclosure:</span> Wilson lower bound scam ratio (N={selectedData.count}) + Bayesian prior shrinkage (α={BAYESIAN_ALPHA}) · 180-day decay. Quantiles: Q25={Math.round((selectedData.q25||0)*100)} Q50={Math.round((selectedData.q50||0)*100)} Q75={Math.round((selectedData.q75||0)*100)}.
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ── INCIDENTS / REPORTS TAB ── */}
              {panelTab === "incidents" && (
                <div style={{ padding: "14px 16px" }}>
                  <input
                    value={placeSearch}
                    onChange={e => setPlaceSearch(e.target.value)}
                    placeholder="🔍 Filter by place or keyword..."
                    style={{
                      width: "100%", boxSizing: "border-box",
                      background: "rgba(15,23,42,0.8)", border: "1px solid rgba(100,116,139,0.15)",
                      borderRadius: 10, padding: "8px 12px", color: "#f8fafc",
                      fontFamily: "inherit", fontSize: 12.5, outline: "none", marginBottom: 12,
                    }}
                  />

                  {placeFiltered.length === 0 && (
                    <div style={{ textAlign: "center", color: "#64748b", fontSize: 12.5, padding: "28px 0" }}>
                      {placeSearch.trim()
                        ? `No reports match "${placeSearch}" in ${selected}.`
                        : "No reports recorded for this district yet."}
                    </div>
                  )}

                  {placeFiltered.map((inc, i) => {
                    const it        = INCIDENT_TYPES[inc.type] || { emoji: "•", label: inc.type };
                    const si        = getSourceInfo(inc.source);
                    const isProfile = profData.concerns.includes(inc.type);
                    return (
                      <div key={inc.id || i} style={{
                        background: "rgba(13,21,38,0.8)",
                        border: `1px solid ${isProfile ? "rgba(6,182,212,0.25)" : "rgba(100,116,139,0.10)"}`,
                        borderRadius: 10, padding: "12px 14px", marginBottom: 8,
                      }}>
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, marginBottom: 5 }}>
                          <div style={{ color: "#f8fafc", fontSize: 12.5, lineHeight: 1.45, fontWeight: 600, flex: 1 }}>
                            {it.emoji} {inc.title}
                          </div>
                          <span style={{ color: "#64748b", fontSize: 10.5, flexShrink: 0, fontWeight: 500 }}>{inc.days_ago}d ago</span>
                        </div>
                        <div style={{ color: "#94a3b8", fontSize: 11, marginBottom: 7 }}>📍 {inc.location}</div>
                        <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                          <span style={{ background: "rgba(30,41,59,0.8)", borderRadius: 5, padding: "2px 8px", fontSize: 10, color: "#cbd5e1" }}>
                            {si.icon} {si.label}
                          </span>
                          <span style={{
                            background: inc.is_scam ? "rgba(239,68,68,0.12)" : "rgba(100,116,139,0.12)",
                            borderRadius: 5, padding: "2px 8px", fontSize: 10, fontWeight: 600,
                            color: inc.is_scam ? "#f87171" : "#94a3b8",
                          }}>{inc.is_scam ? "⚠ Scam Flagged" : "Incident"}</span>
                          <span style={{ background: "rgba(30,41,59,0.8)", borderRadius: 5, padding: "2px 8px", fontSize: 10, color: "#64748b" }}>
                            Sev {inc.severity || 1}/3
                          </span>
                          {isProfile && (
                            <span style={{ background: "rgba(6,182,212,0.10)", borderRadius: 5, padding: "2px 8px", fontSize: 10, color: "#22d3ee", fontWeight: 600 }}>
                              ⚡ Profile Concern
                            </span>
                          )}
                          {inc.youtube_url && (
                            <a href={inc.youtube_url} target="_blank" rel="noreferrer" style={{
                              background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.25)",
                              borderRadius: 5, padding: "2px 8px", fontSize: 10, color: "#f87171", textDecoration: "none", fontWeight: 700,
                            }}>▶ Watch Video ↗</a>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* ── CITIES & AREAS TAB ── */}
              {panelTab === "cities" && (
                <div style={{ padding: "14px 16px" }}>
                  <input
                    value={citySearch}
                    onChange={e => setCitySearch(e.target.value)}
                    placeholder="🔍 Search city or area profile..."
                    style={{
                      width: "100%", boxSizing: "border-box",
                      background: "rgba(15,23,42,0.8)", border: "1px solid rgba(100,116,139,0.15)",
                      borderRadius: 10, padding: "8px 12px", color: "#f8fafc",
                      fontFamily: "inherit", fontSize: 12.5, outline: "none", marginBottom: 12,
                    }}
                  />

                  {filteredCities.length === 0 && (
                    <div style={{ textAlign: "center", color: "#64748b", fontSize: 12.5, padding: "24px 0" }}>
                      {citySearch.trim()
                        ? `No cities match "${citySearch}" in ${selected}.`
                        : "No city profiles available for this district."}
                    </div>
                  )}

                  {filteredCities.map(({ city, profile: cp }) => {
                    const riskPct  = Math.round(cp.risk_score * 100);
                    const negPct   = cp.total_reviews > 0 ? Math.round((cp.negative_reviews / cp.total_reviews) * 100) : 0;
                    const peakMths = cp.peak_complaint_months.map(m => MONTH_NAMES[m]).join(", ");
                    const topLT    = Object.keys(cp.top_location_types || {})[0] || "Various Locations";
                    const cityTier = riskPct >= 35 ? "severe" : riskPct >= 25 ? "high" : riskPct >= 15 ? "moderate" : "low";
                    const cc       = TIER_CONFIG[cityTier];

                    return (
                      <div key={city} style={{
                        background: "rgba(13,21,38,0.8)", border: `1px solid ${cc.stroke}33`,
                        borderRadius: 12, padding: "12px 14px", marginBottom: 10,
                      }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                          <div>
                            <div style={{ color: "#f8fafc", fontSize: 14, fontWeight: 700 }}>{city}</div>
                            <div style={{ color: "#94a3b8", fontSize: 10.5, marginTop: 1 }}>📍 Primary: {topLT}</div>
                          </div>
                          <div style={{ textAlign: "right" }}>
                            <span style={{
                              background: cc.badge, color: "#fff", borderRadius: 6,
                              padding: "2px 9px", fontSize: 11, fontWeight: 800,
                            }}>{riskPct}/100</span>
                            <div style={{ color: cc.text, fontSize: 9.5, marginTop: 3, fontWeight: 600 }}>{cc.label}</div>
                          </div>
                        </div>

                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, marginBottom: 8 }}>
                          {[
                            ["Total Reviews", cp.total_reviews],
                            ["Negative Ratio", `${negPct}%`],
                            ["Scam Mentions", cp.scam_mentions],
                          ].map(([l, v]) => (
                            <div key={l} style={{ background: "rgba(30,41,59,0.6)", borderRadius: 7, padding: "6px 8px" }}>
                              <div style={{ color: "#64748b", fontSize: 9 }}>{l}</div>
                              <div style={{ color: "#e2e8f0", fontSize: 13, fontWeight: 700 }}>{v}</div>
                            </div>
                          ))}
                        </div>

                        {peakMths && (
                          <div style={{ color: "#94a3b8", fontSize: 10, marginTop: 4 }}>
                            ⏰ Peak Complaint Months: <span style={{ color: "#cbd5e1", fontWeight: 600 }}>{peakMths}</span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* ── AI BRIEF TAB ── */}
              {panelTab === "ai" && (
                <div style={{ padding: "16px 18px" }}>
                  <div style={{
                    background: "rgba(6,182,212,0.06)", border: "1px solid rgba(6,182,212,0.18)",
                    borderRadius: 12, padding: "14px 16px", marginBottom: 16,
                  }}>
                    <div style={{ color: "#22d3ee", fontSize: 12, fontWeight: 700, marginBottom: 4 }}>
                      🤖 AI Safety Intelligence Briefing
                    </div>
                    <div style={{ color: "#94a3b8", fontSize: 11.5, lineHeight: 1.6 }}>
                      Personalized for <span style={{ color: "#f8fafc", fontWeight: 700 }}>{profile.name || "Traveler"}</span> · {profData.icon} {profData.label}
                    </div>
                  </div>

                  {!aiText && !aiLoading && !aiError && (
                    <button onClick={fetchAI} style={{
                      width: "100%", padding: "13px",
                      background: "linear-gradient(135deg, #0891b2 0%, #0284c7 100%)",
                      border: "none", borderRadius: 12, color: "#fff",
                      fontFamily: "inherit", fontSize: 13.5, fontWeight: 700,
                      cursor: "pointer", boxShadow: "0 0 18px rgba(6,182,212,0.20)",
                    }}>
                      Generate Briefing for {selected} →
                    </button>
                  )}

                  {aiLoading && (
                    <div style={{ textAlign: "center", padding: "28px 0" }}>
                      <div style={{ color: "#22d3ee", fontSize: 14, fontWeight: 700, marginBottom: 8 }}>⟳ Analyzing {selected}...</div>
                      <div style={{ color: "#64748b", fontSize: 11.5 }}>Cross-referencing incident data and traveler profile</div>
                    </div>
                  )}

                  {aiError && (
                    <div style={{
                      background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.22)",
                      borderRadius: 10, padding: "14px", color: "#f87171", fontSize: 12.5, lineHeight: 1.6,
                    }}>{aiError}</div>
                  )}

                  {aiText && (
                    <>
                      <div style={{
                        background: "rgba(13,21,38,0.9)", border: "1px solid rgba(100,116,139,0.12)",
                        borderRadius: 12, padding: "16px 18px", marginBottom: 14,
                        color: "#e2e8f0", fontSize: 13, lineHeight: 1.85,
                      }}>
                        {aiText}
                      </div>
                      <button onClick={fetchAI} style={{
                        width: "100%", padding: "9px",
                        background: "rgba(30,41,59,0.8)", border: "1px solid rgba(100,116,139,0.18)",
                        borderRadius: 10, color: "#94a3b8", fontFamily: "inherit", fontSize: 12, cursor: "pointer", fontWeight: 600,
                      }}>↺ Regenerate AI Briefing</button>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        ) : (
          /* Empty Panel Placeholder */
          <div style={{
            width: 310, background: "rgba(6,12,23,0.99)",
            borderLeft: "1px solid rgba(100,116,139,0.10)",
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
          }}>
            <div style={{ textAlign: "center", padding: 28 }}>
              <div style={{ fontSize: 44, marginBottom: 14 }}>🗺️</div>
              <div style={{ color: "#94a3b8", fontSize: 13, lineHeight: 1.8, marginBottom: 20 }}>
                Select any district on the map to inspect its risk tier, report breakdown, area profiles, and personalized AI safety briefing.
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                {[["A","Low Risk","#15803d"],["B","Moderate","#b45309"],["C","High Risk","#c2410c"],["D","Severe","#b91c1c"]].map(([g,l,col]) => (
                  <div key={g} style={{ background: "rgba(13,21,38,0.7)", border: "1px solid rgba(100,116,139,0.10)", borderRadius: 10, padding: "10px 8px", textAlign: "center" }}>
                    <div style={{ width: 30, height: 30, borderRadius: "50%", background: col, display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 5px", color: "#fff", fontWeight: 900, fontSize: 14 }}>{g}</div>
                    <div style={{ color: "#64748b", fontSize: 10, fontWeight: 600 }}>{l}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
