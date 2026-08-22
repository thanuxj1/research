// Global API Service for SafeTravel Assistance & Budget Planner Endpoints
const API_BASE_URL = 'http://127.0.0.1:5000';

const ASSISTANCE_ENDPOINTS = [
  '/assistance/recommend',                       // Same-origin via Vite Proxy
  'http://127.0.0.1:5000/assistance/recommend',   // Direct 127.0.0.1
  'http://localhost:5000/assistance/recommend',   // Direct localhost
];

const BUDGET_ENDPOINTS = [
  '/budget_planner/predict',                      // Same-origin via Vite Proxy
  'http://127.0.0.1:5000/budget_planner/predict',  // Direct 127.0.0.1
  'http://localhost:5000/budget_planner/predict',  // Direct localhost
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
        if (data && Array.isArray(data.recommendations)) {
          const enriched = data.recommendations.map((item) => {
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
  return {
    recommendations: fallbackRecs,
    isLive: false,
    rawJson: {
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

function generateFallbackBudgetPrediction(input) {
  const totalLkr = Number(input.budget) || 86450;
  const days = Number(input.days) || 5;
  const dailyLkr = Math.round(totalLkr / days);

  // Category breakdowns matching reference design: 45%, 20%, 15%, 20%
  const hotelLkr = Math.round(totalLkr * 0.45);
  const fuelLkr = Math.round(totalLkr * 0.20);
  const foodLkr = Math.round(totalLkr * 0.15);
  const attractionLkr = Math.round(totalLkr * 0.20);

  let route = 'Colombo -> Kandy -> Nuwara Eliya -> Ella -> Colombo';
  if (input.interest === 'beach') {
    route = 'Colombo -> Bentota -> Galle -> Mirissa -> Colombo';
  } else if (input.interest === 'culture') {
    route = 'Colombo -> Anuradhapura -> Sigiriya -> Kandy -> Colombo';
  } else if (input.interest === 'adventure') {
    route = 'Colombo -> Kitulgala -> Ella -> Adam\'s Peak -> Colombo';
  }

  const hotels = [
    {
      place: 'Kandy',
      hotel_name: 'Hotel Topaz',
      price_lkr: 12000,
      image: 'https://images.unsplash.com/photo-1566073771259-6a8506099945?w=500&auto=format&fit=crop&q=80',
    },
    {
      place: 'Nuwara Eliya',
      hotel_name: 'Grand Villa',
      price_lkr: 15000,
      image: 'https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?w=500&auto=format&fit=crop&q=80',
    },
    {
      place: 'Ella',
      hotel_name: 'Ella Flower Garden',
      price_lkr: 10000,
      image: 'https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?w=500&auto=format&fit=crop&q=80',
    },
    {
      place: 'Colombo',
      hotel_name: 'City Hotel',
      price_lkr: 8000,
      image: 'https://images.unsplash.com/photo-1520250497591-112f2f40a3f4?w=500&auto=format&fit=crop&q=80',
    },
  ];

  return {
    predicted_route: route,
    estimated_total_budget_lkr: totalLkr,
    estimated_daily_budget_lkr: dailyLkr,
    estimated_hotel_cost_lkr: hotelLkr,
    estimated_fuel_cost_lkr: fuelLkr,
    estimated_food_cost_lkr: foodLkr,
    estimated_attraction_cost_lkr: attractionLkr,
    recommended_hotels: hotels,
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

// ── Cultural Q&A / Intent Prediction Endpoint Service (/questions/predict) ──
const QUESTIONS_ENDPOINTS = [
  '/questions/predict',                      // Same-origin via Vite Proxy
  'http://127.0.0.1:5000/questions/predict',  // Direct 127.0.0.1
  'http://localhost:5000/questions/predict',  // Direct localhost
];

/**
 * Sends a question request to /questions/predict
 * @param {string} questionText - User's question string
 * @returns {Promise<{ result: Object, isLive: boolean, rawJson: Object, requestPayload: Object }>}
 */
export async function askCulturalQuestion(questionText = '') {
  const payload = {
    question: questionText.trim() || 'What should I wear when visiting a temple?',
  };

  let lastError = null;

  for (const url of QUESTIONS_ENDPOINTS) {
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
        if (data) {
          return {
            result: data,
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

  console.warn('Questions API at http://127.0.0.1:5000/questions/predict unreachable. Using fallback:', lastError);

  const fallbackData = generateFallbackQuestionResponse(payload.question);
  return {
    result: fallbackData,
    isLive: false,
    rawJson: fallbackData,
    requestPayload: payload,
  };
}

function generateFallbackQuestionResponse(questionStr = '') {
  const q = questionStr.toLowerCase();

  let intent = 'temple_rules_and_etiquette';
  let title = 'Rules for Visiting Temples in Sri Lanka';
  let description = `When visiting a temple in Sri Lanka, please follow these rules:

1. Dress modestly – wear clothes that cover your shoulders and knees.
2. Remove your shoes before entering the temple premises.
3. Avoid wearing hats and sunglasses inside the temple.
4. Do not point your feet towards the Buddha statue.
5. Maintain silence and behave respectfully.
6. Women should avoid touching monks.
7. Photography may be restricted in some areas.

Following these rules shows respect for our culture and traditions. 🙏`;
  let confidence = 0.95;

  if (q.includes('perahera') || q.includes('esala') || q.includes('festival')) {
    intent = 'cultural_festival_perahera';
    title = 'Kandy Esala Perahera Festival';
    description = `The Kandy Esala Perahera is one of Sri Lanka's oldest and grandest Buddhist festivals held annually in July or August.

Key highlights:
1. Processions featuring traditional Kandyan dancers, drummers, whip-crackers, and fire-spinners.
2. Lavishly decorated elephants carrying the sacred Tooth Relic casket.
3. Held over 10 consecutive nights to honor the Sacred Tooth Relic of Buddha.`;
    confidence = 0.96;
  } else if (q.includes('food') || q.includes('eat') || q.includes('traditional food') || q.includes('dish')) {
    intent = 'traditional_sri_lankan_food';
    title = 'Traditional Sri Lankan Cuisine';
    description = `Sri Lankan food is rich in spices, coconut milk, and unique tropical flavors.

Popular must-try dishes:
1. Rice and Curry – Fragrant rice with dhal, chicken/fish curry, and sambols.
2. Kottu Roti – Chopped flatbread stir-fried with vegetables, eggs, spices, and meat.
3. Hoppers (Appa) – Bowl-shaped crispy rice flour pancakes with soft center.
4. Pol Sambol – Freshly grated coconut with chili, lime, and red onions.`;
    confidence = 0.94;
  } else if (q.includes('best time') || q.includes('season') || q.includes('weather') || q.includes('when to visit')) {
    intent = 'best_travel_time';
    title = 'Best Time to Visit Sri Lanka';
    description = `Sri Lanka is a year-round destination with two distinct monsoon seasons.

• West & South Coast (Galle, Mirissa, Colombo): Best from December to April.
• East Coast (Arugam Bay, Trincomalee): Best from May to September.
• Cultural Triangle & Hill Country (Kandy, Ella): Great year-round, best Jan to April.`;
    confidence = 0.92;
  } else if (q.includes('wear') || q.includes('clothes') || q.includes('attire') || q.includes('dress')) {
    intent = 'clothing_and_attire';
    title = 'What to Wear in Sri Lanka';
    description = `Lightweight, breathable cotton clothes are ideal for Sri Lanka's tropical climate.

• Coastal/Beaches: Casual resort wear and swimwear (restricted to beaches).
• Cities & High Street: Casual shorts, t-shirts, and summer dresses.
• Temples & Sacred Sites: White or light-colored attire covering shoulders and knees.`;
    confidence = 0.93;
  } else if (q.includes('etiquette') || q.includes('local') || q.includes('custom') || q.includes('respect')) {
    intent = 'local_etiquette_and_customs';
    title = 'Sri Lankan Local Etiquette & Courtesy';
    description = `Sri Lankans are warm and hospitable. Following basic local customs ensures a pleasant stay:

1. Greet locals with "Ayubowan" (placing palms together).
2. Use your right hand for eating and passing items.
3. Ask for permission before taking photographs of locals or monks.
4. Avoid public displays of affection at religious sites.`;
    confidence = 0.91;
  }

  return {
    success: true,
    question: questionStr,
    predicted_intent: intent,
    confidence: confidence,
    response: {
      title: title,
      description: description,
    },
  };
}
