// Global API Service for SafeTravel Assistance & Budget Planner Endpoints
const API_BASE_URL = 'http://127.0.0.1:5001';

const ASSISTANCE_ENDPOINTS = [
  '/assistance/recommend',                       // Same-origin via Vite Proxy
  'http://127.0.0.1:5001/assistance/recommend',   // Direct 127.0.0.1
  'http://localhost:5001/assistance/recommend',   // Direct localhost
  'http://127.0.0.1:5000/assistance/recommend',   // Secondary fallback
];

const BUDGET_ENDPOINTS = [
  '/budget_planner/predict',                      // Same-origin via Vite Proxy
  'http://127.0.0.1:5001/budget_planner/predict',  // Direct 127.0.0.1
  'http://localhost:5001/budget_planner/predict',  // Direct localhost
  'http://127.0.0.1:5000/budget_planner/predict',  // Secondary fallback
];

const CULTURAL_ENDPOINTS = [
  '/questions/predict',                           // Same-origin via Vite Proxy
  'http://127.0.0.1:5001/questions/predict',       // Direct 127.0.0.1
  'http://localhost:5001/questions/predict',       // Direct localhost
  'http://127.0.0.1:5000/questions/predict',       // Secondary fallback
];

// Comprehensive place metadata mapping for all Sri Lankan destinations
export const DESTINATION_DETAILS = {
  'Galle': {
    place: 'Galle',
    desc: 'Historic coastal city with Dutch architecture, beaches and rich culture.',
    image: '/images/galle.png',
  },
  'Nuwara Eliya': {
    place: 'Nuwara Eliya',
    desc: 'Little England of Sri Lanka with cool climate and tea estates.',
    image: '/images/nuwara_eliya.png',
  },
  'Mirissa': {
    place: 'Mirissa',
    desc: 'Relaxing beach destination famous for whale watching and surf breaks.',
    image: '/images/mirissa.png',
  },
  'Bentota': {
    place: 'Bentota',
    desc: 'Prime beach resort town known for water sports, lagoons, and golden sands.',
    image: '/images/mirissa.png',
  },
  'Arugam Bay': {
    place: 'Arugam Bay',
    desc: 'World-famous surfing haven on the east coast with relaxed beach vibes.',
    image: '/images/mirissa.png',
  },
  'Anuradhapura': {
    place: 'Anuradhapura',
    desc: 'Sacred ancient capital with magnificent stupas, ruins, and holy Bodhi tree.',
    image: '/images/sigiriya.png',
  },
  'Polonnaruwa': {
    place: 'Polonnaruwa',
    desc: 'Royal medieval kingdom with preserved stone temples and Buddha statues.',
    image: '/images/sigiriya.png',
  },
  'Jaffna': {
    place: 'Jaffna',
    desc: 'Cultural heart of northern Sri Lanka with colorful Kovils and unique cuisine.',
    image: '/images/galle.png',
  },
  'Trincomalee': {
    place: 'Trincomalee',
    desc: 'Deep natural harbor with Nilaveli beaches and Koneswaram Hindu temple.',
    image: '/images/mirissa.png',
  },
  'Yala': {
    place: 'Yala',
    desc: 'Sri Lanka’s premier wildlife national park, world-renowned for leopard sightings.',
    image: '/images/ella.png',
  },
  'Hikkaduwa': {
    place: 'Hikkaduwa',
    desc: 'Lively southern beach town popular for coral reefs, turtles, and nightlife.',
    image: '/images/mirissa.png',
  },
  'Dambulla': {
    place: 'Dambulla',
    desc: 'Famous Golden Cave Temple complex filled with ancient Buddhist murals.',
    image: '/images/sigiriya.png',
  },
  'Ella': {
    place: 'Ella',
    desc: 'Beautiful mountain town with waterfalls, tea plantations and scenic views.',
    image: '/images/ella.png',
  },
  'Sigiriya': {
    place: 'Sigiriya',
    desc: 'Ancient rock fortress and UNESCO World Heritage Site.',
    image: '/images/sigiriya.png',
  },
  'Kandy': {
    place: 'Kandy',
    desc: 'Cultural capital with sacred Temple of the Tooth and royal botanical gardens.',
    image: '/images/nuwara_eliya.png',
  },
};

/**
 * Calculates crowd temporal parameters (month, day_of_week, is_weekend) from a date string (YYYY-MM-DD)
 */
export function calculateCrowdFromDate(dateString) {
  let d = new Date();
  if (dateString) {
    const parts = dateString.split('-');
    if (parts.length === 3) {
      d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
    }
  }

  const month = d.getMonth() + 1; // 1-12
  const dayOfWeek = d.getDay();   // 0 (Sun) - 6 (Sat)
  const isWeekend = (dayOfWeek === 0 || dayOfWeek === 6) ? 1 : 0;

  return {
    month: month,
    day_of_week: dayOfWeek,
    is_weekend: isWeekend,
    lag_1: 100,
    lag_2: 100,
    lag_3: 100,
  };
}

/**
 * Automatically computes current temporal parameters (month, day_of_week, is_weekend)
 * and realistic live weather conditions for Sri Lanka.
 */
export function getAutomaticWeatherAndCrowd() {
  const now = new Date();
  const month = now.getMonth() + 1; // 1-12
  const dayOfWeek = now.getDay();   // 0 (Sun) - 6 (Sat)
  const isWeekend = (dayOfWeek === 0 || dayOfWeek === 6) ? 1 : 0;

  return {
    weather: {
      rainfall_mm: 2.0,
      temperature_c: 28.5,
    },
    crowd: {
      month: month,
      day_of_week: dayOfWeek,
      is_weekend: isWeekend,
      lag_1: 100,
      lag_2: 100,
      lag_3: 100,
    },
  };
}

/**
 * Sends a recommendation request to the Python backend API at /assistance/recommend.
 */
export async function getRecommendations(userText = '', overrideParams = {}) {
  const autoData = getAutomaticWeatherAndCrowd();

  const crowdParams = overrideParams.plannedDate
    ? calculateCrowdFromDate(overrideParams.plannedDate)
    : overrideParams.crowd || autoData.crowd;

  const payload = {
    user_text: userText,
    origin: overrideParams.origin || 'Colombo',
    days: overrideParams.days || 3,
    transport_mode: overrideParams.transport_mode || 'car',
    weather: overrideParams.weather || autoData.weather,
    crowd: crowdParams,
  };

  let lastError = null;

  for (const url of ASSISTANCE_ENDPOINTS) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        const data = await response.json();
        console.log("Backend Raw Response Data:", data);
        console.log("Route Recommendations:", data?.route_recommendations);
        console.log("Destination Recommendations:", data?.recommendations);

        if (data && (Array.isArray(data.recommendations) || Array.isArray(data.route_recommendations))) {
          const recs = Array.isArray(data.recommendations) ? data.recommendations : [];
          const routeRecs = Array.isArray(data.route_recommendations) ? data.route_recommendations : [];

          const enriched = recs.map((item) => {
            const pName = item.place || item.name || 'Galle';
            const meta = DESTINATION_DETAILS[pName] || {
              desc: 'Top travel destination in Sri Lanka.',
              image: `/images/${pName.toLowerCase().replace(/\s+/g, '_')}.png`,
            };

            const numScore = item.score != null ? Math.round(item.score) : 65;
            const numCrowd = item.crowd != null ? parseFloat(Number(item.crowd).toFixed(2)) : 100;
            const weatherVal = item.weather || 'Low';

            return {
              ...item,
              place: pName,
              desc: meta.desc,
              image: meta.image,
              score: numScore,
              crowd: numCrowd,
              weather: weatherVal,
              crowd_label: item.crowd_label || (numCrowd < 110 ? 'Low' : numCrowd < 200 ? 'Moderate' : 'High'),
            };
          });

          return {
            recommendations: enriched,
            route_recommendations: routeRecs,
            isLive: true,
            rawJson: data,
            requestPayload: payload,
            errorDetail: null,
          };
        }
      } else {
        lastError = `HTTP ${response.status} ${response.statusText}`;
      }
    } catch (err) {
      lastError = err.message || 'Network error';
    }
  }

  const fallbackRecs = generateFallbackRecommendations(userText);
  const fallbackRoutes = generateFallbackRouteRecommendations(userText, payload.days);
  return {
    recommendations: fallbackRecs,
    route_recommendations: fallbackRoutes,
    isLive: false,
    rawJson: {
      route_recommendations: fallbackRoutes,
      recommendations: fallbackRecs.map(({ place, crowd, weather, score }) => ({
        place,
        crowd,
        weather,
        score,
      })),
    },
    requestPayload: payload,
    errorDetail: lastError,
  };
}

function generateFallbackRouteRecommendations(userText = '', days = 3) {
  return [
    {
      rank: 1,
      route: ['Colombo', 'Kandy', 'Nuwara Eliya', 'Ella'],
      route_display: 'Colombo → Kandy → Nuwara Eliya → Ella',
      overall_route_score: 92,
      decision: 'Highly Recommended',
      total_distance_km: 246,
      total_travel_time_hours: 6.8,
      total_travel_time: '6h 48m',
      days: days,
      feasible: true,
      segments: [
        { from: 'Colombo', to: 'Kandy', distance_km: 115, estimated_travel_time: '2h 34m', is_estimated_distance: false, warnings: [] },
        { from: 'Kandy', to: 'Nuwara Eliya', distance_km: 76, estimated_travel_time: '1h 41m', is_estimated_distance: false, warnings: [] },
        { from: 'Nuwara Eliya', to: 'Ella', distance_km: 55, estimated_travel_time: '1h 14m', is_estimated_distance: false, warnings: [] }
      ],
      daily_plan: [
        { day: 1, route: 'Colombo → Kandy', destinations: ['Colombo', 'Kandy'], travel_time: '2h 34m', activities: [{ name: 'Temple of the Tooth', time: '15:00-17:00' }] },
        { day: 2, route: 'Kandy → Nuwara Eliya', destinations: ['Kandy', 'Nuwara Eliya'], travel_time: '1h 41m', activities: [{ name: 'Pedro Tea Estate', time: '09:30-11:30' }] },
        { day: 3, route: 'Nuwara Eliya → Ella', destinations: ['Nuwara Eliya', 'Ella'], travel_time: '1h 14m', activities: [{ name: 'Nine Arches Bridge', time: '14:00-16:30' }] }
      ],
      why_recommended: [
        'Strong match for quiet and cool-weather preferences',
        'Route minimizes unnecessary backtracking',
        'Destination sequence is geographically efficient',
        'Weather conditions are suitable across the route',
        'Travel time is feasible within the selected duration'
      ],
      tradeoffs: [
        'Some route segments require longer travel time'
      ]
    }
  ];
}

/**
 * Sends a budget planner prediction request to /budget_planner/predict.
 *
 * @param {Object} inputData
 * @param {number} inputData.budget - Total budget in LKR (e.g. 120000)
 * @param {number} inputData.days - Trip duration in days (e.g. 5)
 * @param {string} inputData.interest - Primary interest (e.g. "nature", "culture", "beach")
 * @param {string} inputData.travel_type - Travel group (e.g. "family", "solo", "couple")
 * @param {string} inputData.transport_mode - Transport (e.g. "car", "tuk_tuk", "train")
 * @returns {Promise<{ prediction: Object, isLive: boolean, rawJson: Object, requestPayload: Object }>}
 */
export async function predictBudgetPlan(inputData = {}) {
  const payload = {
    budget: Number(inputData.budget) || 120000,
    days: Number(inputData.days) || 5,
    interest: inputData.interest || 'nature',
    travel_type: inputData.travel_type || 'family',
    transport_mode: inputData.transport_mode || 'car',
  };

  let lastError = null;

  for (const url of BUDGET_ENDPOINTS) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        const data = await response.json();
        if (data && data.prediction) {
          return {
            prediction: data.prediction,
            isLive: true,
            rawJson: data,
            requestPayload: payload,
          };
        }
      } else {
        lastError = `HTTP ${response.status} ${response.statusText}`;
      }
    } catch (err) {
      lastError = err.message || 'Network error';
    }
  }

  console.warn('Budget Planner API at http://127.0.0.1:5000/budget_planner/predict unreachable. Using fallback:', lastError);

  // Fallback intelligent prediction matching backend shape
  const fallbackPrediction = generateFallbackBudgetPrediction(payload);
  const fallbackRawJson = {
    success: true,
    input: payload,
    prediction: fallbackPrediction,
  };

  return {
    prediction: fallbackPrediction,
    isLive: false,
    rawJson: fallbackRawJson,
    requestPayload: payload,
  };
}

/**
 * Sends a cultural question request to /questions/predict.
 */
export async function askCulturalQuestion(questionText = '') {
  const payload = { question: questionText };
  let lastError = null;

  for (const url of CULTURAL_ENDPOINTS) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        const data = await response.json();
        if (data) {
          return {
            result: data.result || data,
            isLive: true,
            rawJson: data,
            requestPayload: payload,
          };
        }
      } else {
        lastError = `HTTP ${response.status} ${response.statusText}`;
      }
    } catch (err) {
      lastError = err.message || 'Network error';
    }
  }

  const fallbackResult = generateFallbackCulturalAnswer(questionText);
  return {
    result: fallbackResult,
    isLive: false,
    rawJson: { result: fallbackResult },
    requestPayload: payload,
    errorDetail: lastError,
  };
}

function generateFallbackCulturalAnswer(query = '') {
  const q = query.toLowerCase();

  if (q.includes('food') || q.includes('eat') || q.includes('rice') || q.includes('curry')) {
    return {
      predicted_intent: 'cultural_food',
      confidence: 0.95,
      response: {
        title: 'Traditional Sri Lankan Cuisine',
        description: 'Rice and Curry is the staple dish of Sri Lanka, usually eaten by hand using the right hand. Kottu Roti, Hoppers (Appa), and String Hoppers are popular street food favorites.',
        guidance: [
          'Always use your right hand when eating food traditionally.',
          'Try authentic local eateries for Kottu Roti and fresh seafood.',
          'Be prepared for spicy flavors — ask for less spice if sensitive.'
        ],
        avoid: [
          'Do not use your left hand to pass food or eat.',
          'Avoid drinking unboiled tap water.'
        ],
        recommended_festivals: ['Avurudu (Sinhala & Tamil New Year Food Table)', 'Vel Festival']
      }
    };
  }

  if (q.includes('perahera') || q.includes('esala') || q.includes('festival') || q.includes('temple')) {
    return {
      predicted_intent: 'cultural_festival',
      confidence: 0.98,
      response: {
        title: 'Kandy Esala Perahera & Temple Etiquette',
        description: 'The Esala Perahera in Kandy is one of South Asia’s oldest and grandest Buddhist festivals, featuring decorated elephants, traditional Kandyan dancers, and drummers paying homage to the Sacred Tooth Relic.',
        guidance: [
          'Dress modestly covering shoulders and knees when visiting temples.',
          'Remove shoes and hats before entering sacred temple precincts.',
          'Book seating in advance for the night perahera processions.'
        ],
        avoid: [
          'Do not turn your back directly to Buddha statues when posing for photos.',
          'Do not touch or disturb Buddhist monks or religious items.'
        ],
        recommended_festivals: ['Kandy Esala Perahera', 'Vesak Poya', 'Katharagama Festival']
      }
    };
  }

  return {
    predicted_intent: 'cultural_qa',
    confidence: 0.90,
    response: {
      title: 'Sri Lankan Cultural Etiquette & Customs',
      description: 'Sri Lanka is a warm and hospitable country with rich Buddhist, Hindu, Muslim, and Christian heritage. Greeting locals with a smile and a polite "Ayubowan" (May you live long) is warmly welcomed.',
      guidance: [
        'Greet locals with "Ayubowan" joining palms together in front of the chest.',
        'Cover shoulders and knees when visiting all religious sites.',
        'Ask permission before taking photos of local people or monks.'
      ],
      avoid: [
        'Avoid public displays of affection in conservative areas.',
        'Never pose standing beside or with your back facing a Buddha image.',
        'Do not touch someone on the head, as it is considered sacred.'
      ],
      recommended_festivals: ['Vesak Poya', 'Sinhala & Tamil New Year', 'Deepavali']
    }
  };
}

function generateFallbackBudgetPrediction(input) {
  const totalLkr = input.budget;
  const days = input.days;
  const dailyLkr = totalLkr / days;

  // Category breakdowns
  const hotelLkr = totalLkr * 0.45;
  const fuelLkr = totalLkr * 0.18;
  const foodLkr = totalLkr * 0.22;
  const attractionLkr = totalLkr * 0.15;

  let route = 'Colombo -> Kandy -> Ella -> Colombo';
  if (input.interest === 'beach') {
    route = 'Colombo -> Bentota -> Galle -> Mirissa -> Colombo';
  } else if (input.interest === 'culture') {
    route = 'Colombo -> Anuradhapura -> Sigiriya -> Kandy -> Colombo';
  }

  return {
    predicted_route: route,
    estimated_total_budget_lkr: parseFloat(totalLkr.toFixed(2)),
    estimated_daily_budget_lkr: parseFloat(dailyLkr.toFixed(2)),
    estimated_hotel_cost_lkr: parseFloat(hotelLkr.toFixed(2)),
    estimated_fuel_cost_lkr: parseFloat(fuelLkr.toFixed(2)),
    estimated_food_cost_lkr: parseFloat(foodLkr.toFixed(2)),
    estimated_attraction_cost_lkr: parseFloat(attractionLkr.toFixed(2)),
    recommended_hotels: [
      { place: 'Kandy', hotel_name: 'Earl’s Regency Hotel', price_lkr: 18000 },
      { place: 'Ella', hotel_name: '98 Acres Resort & Spa', price_lkr: 22000 },
      { place: 'Sigiriya', hotel_name: 'Aliya Resort & Spa', price_lkr: 16500 },
    ],
  };
}

function generateFallbackRecommendations(userText = '') {
  const query = userText.toLowerCase().trim();

  const baseCatalog = [
    {
      place: 'Galle',
      baseScore: 65,
      crowd_label: 'Low',
      weather: 'Low',
      crowd: 105.93,
      desc: 'Historic coastal city with Dutch architecture, beaches and rich culture.',
      image: '/images/galle.png',
      tags: ['beach', 'coastal', 'heritage', 'culture', 'history', 'dutch'],
    },
    {
      place: 'Nuwara Eliya',
      baseScore: 65,
      crowd_label: 'Low',
      weather: 'Low',
      crowd: 98.9,
      desc: 'Little England of Sri Lanka with cool climate and tea estates.',
      image: '/images/nuwara_eliya.png',
      tags: ['cool', 'highlands', 'tea', 'misty', 'low crowd', 'nature'],
    },
    {
      place: 'Mirissa',
      baseScore: 65,
      crowd_label: 'Low',
      weather: 'Low',
      crowd: 98.24,
      desc: 'Relaxing beach destination famous for whale watching.',
      image: '/images/mirissa.png',
      tags: ['beach', 'ocean', 'sea', 'whale', 'coastal', 'surfing'],
    },
    {
      place: 'Bentota',
      baseScore: 65,
      crowd_label: 'Low',
      weather: 'Low',
      crowd: 98.48,
      desc: 'Prime beach resort town known for water sports and lagoons.',
      image: '/images/mirissa.png',
      tags: ['beach', 'resort', 'water sports'],
    },
    {
      place: 'Arugam Bay',
      baseScore: 65,
      crowd_label: 'Low',
      weather: 'Low',
      crowd: 98.24,
      desc: 'World-famous surfing haven on the east coast with relaxed beach vibes.',
      image: '/images/mirissa.png',
      tags: ['surf', 'beach', 'east coast'],
    },
    {
      place: 'Anuradhapura',
      baseScore: 65,
      crowd_label: 'Low',
      weather: 'Low',
      crowd: 98.24,
      desc: 'Sacred ancient capital with magnificent stupas and ruins.',
      image: '/images/sigiriya.png',
      tags: ['ancient', 'heritage', 'temple'],
    },
    {
      place: 'Ella',
      baseScore: 60,
      crowd_label: 'Moderate',
      weather: 'Moderate',
      crowd: 78.71,
      desc: 'Beautiful mountain town with waterfalls, tea plantations and scenic views.',
      image: '/images/ella.png',
      tags: ['mountain', 'low crowd', 'waterfall', 'nature', 'hike', 'tea'],
    },
    {
      place: 'Sigiriya',
      baseScore: 50,
      crowd_label: 'Low',
      weather: 'Low',
      crowd: 126.57,
      desc: 'Ancient rock fortress and UNESCO World Heritage Site.',
      image: '/images/sigiriya.png',
      tags: ['fortress', 'rock', 'heritage', 'unesco', 'ancient', 'history'],
    },
    {
      place: 'Kandy',
      baseScore: 45,
      crowd_label: 'Moderate',
      weather: 'Moderate',
      crowd: 116.18,
      desc: 'Cultural capital with sacred Temple of the Tooth.',
      image: '/images/nuwara_eliya.png',
      tags: ['culture', 'temple', 'kandy'],
    },
  ];

  if (!query) {
    return baseCatalog;
  }

  const scored = baseCatalog.map((item) => {
    let score = item.baseScore;
    const matchCount = item.tags.filter((tag) => query.includes(tag)).length;
    score += matchCount * 5;
    return {
      ...item,
      score: Math.min(score, 99),
    };
  });

  return scored.sort((a, b) => b.score - a.score);
}
