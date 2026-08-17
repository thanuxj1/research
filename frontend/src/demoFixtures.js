/**
 * ╔══════════════════════════════════════════════════════════════════════════╗
 * ║  DEMO FIXTURES — ALL DATA IN THIS FILE IS INVENTED                     ║
 * ║                                                                          ║
 * ║  These incidents were hand-authored as plausible illustrative examples.  ║
 * ║  They are NOT sourced from any database, news article, traveller report, ║
 * ║  or real-world record.  None of the monetary figures, locations, source  ║
 * ║  badges, or helpful-vote counts reflect actual events.                   ║
 * ║                                                                          ║
 * ║  Loading condition: only imported when ?demo=1 is in the URL             ║
 * ║  OR when VITE_DEMO_MODE=true in the Vite environment.                   ║
 * ║  The live application NEVER falls back to this data automatically.       ║
 * ╚══════════════════════════════════════════════════════════════════════════╝
 */

export const DEMO_INCIDENTS = {
  Colombo: [
    { id:"C1",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:5,   title:"Gem shop fraud near Pettah — tourist lost $2,400",                  source:"adaderana",   location:"Pettah", helpful_votes:12 },
    { id:"C2",  type:"tuk_tuk_scam",       severity:2, is_scam:true,  days_ago:12,  title:"Airport tuk-tuk demanded 10× metered fare to Colombo 3",            source:"tripadvisor", location:"BIA Airport Road", helpful_votes:28 },
    { id:"C3",  type:"accommodation_scam", severity:2, is_scam:true,  days_ago:20,  title:"Fake guesthouse listing — different property on arrival",            source:"google_maps", location:"Colombo 3", helpful_votes:7 },
    { id:"C4",  type:"harassment",         severity:2, is_scam:false, days_ago:8,   title:"Persistent vendor harassment at Galle Face Green",                   source:"reddit",      location:"Galle Face Green", helpful_votes:45 },
    { id:"C5",  type:"transport_fraud",    severity:2, is_scam:true,  days_ago:30,  title:"Metered taxi refusing to use meter — Fort to Cinnamon Grand",        source:"tripadvisor", location:"Colombo Fort", helpful_votes:19 },
    { id:"C6",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:60,  title:"Gem investment scheme near Fort — certificates confirmed fake",       source:"adaderana",   location:"Colombo Fort", helpful_votes:8 },
    { id:"C7",  type:"unsafe_area",        severity:2, is_scam:false, days_ago:15,  title:"Pickpocket at Pettah bus stand during peak hour",                    source:"reddit",      location:"Pettah Bus Stand", helpful_votes:31 },
    { id:"C8",  type:"overcharging",       severity:1, is_scam:true,  days_ago:45,  title:"Tourist menu 3× local price at Fort area seafood restaurant",        source:"google_maps", location:"Colombo Fort", helpful_votes:14 },
    { id:"C9",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:3,   title:"Gem scam exposed — how it works in Colombo",                         source:"youtube",     location:"Colombo", youtube_url:"https://www.youtube.com/watch?v=X-PWzRBmTCk", helpful_votes:200 },
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
    { id:"K7",  type:"transport_fraud",    severity:2, is_scam:true,  days_ago:18,  title:"Kandy tuk-tuk scams explained — tourist warning video",              source:"youtube",     location:"Kandy", youtube_url:"https://www.youtube.com/watch?v=kYxRk5_v8cE", helpful_votes:180 },
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
    { id:"GA2", type:"accommodation_scam", severity:2, is_scam:true,  days_ago:50,  title:"Negombo hotel booking not as advertised — mold, no AC",               source:"tripadvisor", location:"Negombo Beach", helpful_votes:21 },
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
    { id:"A4",  type:"fake_guide",         severity:2, is_scam:true,  days_ago:22,  title:"Fake monk at Sri Maha Bodhi requesting money for ceremonies",        source:"adaderana",   url:"https://www.adaderana.lk/news.php", location:"Sri Maha Bodhi", helpful_votes:34 },
    { id:"A5",  type:"overcharging",       severity:1, is_scam:true,  days_ago:55,  title:"Tuk-tuk heritage circuit price doubled without notice",               source:"tripadvisor", location:"Anuradhapura", helpful_votes:9 },
  ],
  Badulla: [
    { id:"B1",  type:"transport_fraud",    severity:1, is_scam:true,  days_ago:20,  title:"Ella station taxi: LKR 2,000 quoted, LKR 5,000 charged on arrival",  source:"reddit",      location:"Ella Train Station", helpful_votes:33 },
    { id:"B2",  type:"accommodation_scam", severity:1, is_scam:true,  days_ago:45,  title:"Ella guesthouse double booking — stranded tourists",                  source:"tripadvisor", location:"Ella", helpful_votes:15 },
    { id:"B3",  type:"overcharging",       severity:1, is_scam:true,  days_ago:10,  title:"Nine Arches Bridge unofficial guide fee demanded",                    source:"google_maps", location:"Nine Arches Bridge", helpful_votes:10 },
    { id:"B4",  type:"fake_guide",         severity:2, is_scam:true,  days_ago:35,  title:"Unlicensed nature guide on Ella Rock trails — no first aid kit",      source:"reddit",      location:"Ella Rock Trails", helpful_votes:24 },
    { id:"B5",  type:"transport_fraud",    severity:1, is_scam:true,  days_ago:5,   title:"Ella tuk-tuk scam — tourist warning investigation",                  source:"youtube",     location:"Ella", youtube_url:"https://www.youtube.com/watch?v=y3OLraXOzKY", helpful_votes:120 },
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
    { id:"R4",  type:"gem_scam",           severity:3, is_scam:true,  days_ago:4,   title:"Ratnapura gem scam: investigative report on fake mine tours",         source:"youtube",     location:"Ratnapura", youtube_url:"https://www.youtube.com/watch?v=dpH-gBBOKEY", helpful_votes:310 },
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
    { id:"T1",  type:"unsafe_area",        severity:1, is_scam:false, days_ago:90,  title:"Tourist police advisory: check restricted zones before travel",       source:"tourist_police_lk", location:"Trincomalee", url:"https://touristpolice.police.lk", helpful_votes:0 },
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
  Kurunegala: [], Monaragala: [], Ampara: [], Batticaloa: [],
  Puttalam: [], "Vanni (Mannar/Vavuniya/Mullaitivu)": [],
};

/** Illustrative review bodies, invented to accompany demo incidents. */
export const DEMO_REVIEW_BODIES = {
  A4:  "Ada Derana reported an incident at Sri Maha Bodhi in Anuradhapura where an individual impersonating a Buddhist monk approached foreign tourists requesting cash donations for 'blessing ceremonies.'",
  C2:  "We arrived at the airport exhausted and a friendly-looking driver offered to take us to Colombo 3. Agreed price was 2,000 LKR but he demanded 20,000 on arrival. Always pre-book through PickMe or Uber.",
  C9:  "YouTube investigation showing how the Colombo gem scam operates from approach to sale.",
  K2:  "Shopkeeper near Kandy Lake showed us GIA certificates that looked official. Bought a 'blue sapphire' for $400. Had it appraised — synthetic glass worth $8.",
  R1:  "Joined a 'gem mine investment tour' in Ratnapura. Invested $8,000. Back home confirmed synthetic corundum worth under $200. Total loss.",
  // Add more as needed for demos
};
