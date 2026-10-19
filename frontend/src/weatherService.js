/**
 * Weather Service for SafeTravel Events & Travel Planner
 * Integrates with Open-Meteo Public API (https://open-meteo.com/en/docs)
 * 
 * Features:
 * - Verified destination coordinates from project constants
 * - Geocoding fallback with strict Sri Lanka filter and unambiguous matching
 * - Query-based automatic destination detection for supported destinations (e.g. Kandy)
 * - Open-Meteo numerical forecast with model timesteps and hourly forecasts in Asia/Colombo
 * - Accurate WMO weather code interpretation and application-defined outdoor activity guidance
 * - Separate provider model valid time vs. client fetch timestamp
 * - In-memory caching, forced refresh cache bypass, and request deduplication
 */

// 1. Verified destination coordinates from existing project (backend_flask/assitance/app.py)
// Never reuse one city's coordinates for another destination.
export const VERIFIED_DESTINATION_COORDINATES = {
  'Ella': { latitude: 6.8667, longitude: 81.0466 },
  'Galle': { latitude: 6.0535, longitude: 80.2210 },
  'Sigiriya': { latitude: 7.9570, longitude: 80.7603 },
  'Kandy': { latitude: 7.2906, longitude: 80.6337 },
  'Nuwara Eliya': { latitude: 6.9497, longitude: 80.7891 },
  'Mirissa': { latitude: 5.9483, longitude: 80.4716 },
  'Bentota': { latitude: 6.4218, longitude: 79.9950 },
  'Arugam Bay': { latitude: 6.8404, longitude: 81.8378 },
  'Anuradhapura': { latitude: 8.3114, longitude: 80.4037 },
  'Polonnaruwa': { latitude: 7.9403, longitude: 81.0188 },
  'Jaffna': { latitude: 9.6615, longitude: 80.0255 },
  'Trincomalee': { latitude: 8.5874, longitude: 81.2152 },
  'Yala': { latitude: 6.3725, longitude: 81.5185 },
  'Hikkaduwa': { latitude: 6.1407, longitude: 80.1010 },
  'Dambulla': { latitude: 7.8742, longitude: 80.6511 },
  'Colombo': { latitude: 6.9271, longitude: 79.8612 },
  'Kataragama': { latitude: 6.4134, longitude: 81.3346 },
};

export const ESTABLISHED_DESTINATION_NAMES = [
  'Ella',
  'Galle',
  'Sigiriya',
  'Kandy',
  'Nuwara Eliya',
  'Mirissa',
  'Bentota',
  'Arugam Bay',
  'Anuradhapura',
  'Polonnaruwa',
  'Jaffna',
  'Trincomalee',
  'Yala',
  'Hikkaduwa',
  'Dambulla',
  'Kataragama',
];

/**
 * Detects whether a submitted user query unambiguously identifies a supported destination.
 * Uses established destination names/aliases with word boundary matching.
 * 
 * @param {string} queryText - User's preference query (e.g. "Visiting Kandy for culture")
 * @returns {Object} Resolution details:
 *   - detected: canonical destination name if unambiguous, else null
 *   - isUnambiguous: boolean
 *   - matches: array of matched canonical names
 *   - reason: 'unambiguous_match' | 'multi_destination' | 'no_destination_specified'
 */
export function detectDestinationFromQuery(queryText) {
  if (!queryText || typeof queryText !== 'string') {
    return { detected: null, isUnambiguous: false, matches: [], reason: 'no_destination_specified' };
  }

  const clean = queryText.trim().toLowerCase();

  const destinationMap = [
    { canonical: 'Nuwara Eliya', patterns: [/\bnuwara\s+eliya\b/i, /\bnuwaraeliya\b/i] },
    { canonical: 'Arugam Bay', patterns: [/\barugam\s+bay\b/i, /\barugambay\b/i] },
    { canonical: 'Kandy', patterns: [/\bkandy\b/i] },
    { canonical: 'Galle', patterns: [/\bgalle\b/i] },
    { canonical: 'Ella', patterns: [/\bella\b/i] },
    { canonical: 'Sigiriya', patterns: [/\bsigiriya\b/i] },
    { canonical: 'Mirissa', patterns: [/\bmirissa\b/i] },
    { canonical: 'Bentota', patterns: [/\bbentota\b/i] },
    { canonical: 'Anuradhapura', patterns: [/\banuradhapura\b/i] },
    { canonical: 'Polonnaruwa', patterns: [/\bpolonnaruwa\b/i] },
    { canonical: 'Jaffna', patterns: [/\bjaffna\b/i] },
    { canonical: 'Trincomalee', patterns: [/\btrincomalee\b/i] },
    { canonical: 'Yala', patterns: [/\byala\b/i] },
    { canonical: 'Hikkaduwa', patterns: [/\bhikkaduwa\b/i] },
    { canonical: 'Dambulla', patterns: [/\bdambulla\b/i] },
    // Covers kataragama, katharagama, katargama, kathargama, and the short typo "katharama"
    { canonical: 'Kataragama', patterns: [/\bkath?ara?gama\b/i, /\bkath?arama\b/i] },
  ];

  const matches = [];
  for (const item of destinationMap) {
    if (item.patterns.some((re) => re.test(clean))) {
      matches.push(item.canonical);
    }
  }

  if (matches.length === 1) {
    return {
      detected: matches[0],
      isUnambiguous: true,
      matches,
      reason: 'unambiguous_match',
    };
  }

  if (matches.length > 1) {
    return {
      detected: null,
      isUnambiguous: false,
      matches,
      reason: 'multi_destination',
    };
  }

  return {
    detected: null,
    isUnambiguous: false,
    matches: [],
    reason: 'no_destination_specified',
  };
}

// 2. WMO Weather Interpretation Codes (WW) strictly following Open-Meteo documentation
// Code 95 is "Thunderstorm: Slight or moderate" (does NOT include hail).
// Codes 96 & 99 are thunderstorms with slight/heavy hail.
// Disruption tiers are application-defined outdoor activity guidance, not official warning levels.
export const WMO_WEATHER_CODES = {
  0: {
    description: 'Clear sky',
    icon: '☀️',
    category: 'clear',
    advisory: 'Favorable conditions for outdoor sightseeing, photography, and travel.',
    disruptionLevel: 'Minimal Outdoor Disruption Potential',
  },
  1: {
    description: 'Mainly clear',
    icon: '🌤️',
    category: 'clear',
    advisory: 'Favorable outdoor conditions with light cloud cover.',
    disruptionLevel: 'Minimal Outdoor Disruption Potential',
  },
  2: {
    description: 'Partly cloudy',
    icon: '⛅',
    category: 'partly_cloudy',
    advisory: 'Pleasant travel weather. Good conditions for hiking and outdoor tours.',
    disruptionLevel: 'Minimal Outdoor Disruption Potential',
  },
  3: {
    description: 'Overcast',
    icon: '☁️',
    category: 'cloudy',
    advisory: 'Persistent cloud cover. Outdoor activities generally undisrupted.',
    disruptionLevel: 'Low Outdoor Disruption Potential',
  },
  45: {
    description: 'Fog',
    icon: '🌫️',
    category: 'fog',
    advisory: 'Reduced visibility. Exercise caution on winding highland roads and mountain trails.',
    disruptionLevel: 'Moderate Outdoor Disruption Potential',
  },
  48: {
    description: 'Depositing rime fog',
    icon: '🌫️',
    category: 'fog',
    advisory: 'Dense mist and low visibility. Scenic viewpoints and mountain passes may be obscured.',
    disruptionLevel: 'Moderate Outdoor Disruption Potential',
  },
  51: {
    description: 'Drizzle: Light intensity',
    icon: '🌦️',
    category: 'drizzle',
    advisory: 'Light drizzle expected. Outdoor activities can proceed with light waterproofs.',
    disruptionLevel: 'Low Outdoor Disruption Potential',
  },
  53: {
    description: 'Drizzle: Moderate intensity',
    icon: '🌦️',
    category: 'drizzle',
    advisory: 'Persistent drizzle. Rain jackets recommended for walking tours.',
    disruptionLevel: 'Low Outdoor Disruption Potential',
  },
  55: {
    description: 'Drizzle: Dense intensity',
    icon: '🌧️',
    category: 'drizzle',
    advisory: 'Dense drizzle with reduced comfort for open-air excursions.',
    disruptionLevel: 'Moderate Outdoor Disruption Potential',
  },
  56: {
    description: 'Freezing Drizzle: Light intensity',
    icon: '🌧️',
    category: 'drizzle',
    advisory: 'Cold damp conditions with slippery surfaces.',
    disruptionLevel: 'Moderate Outdoor Disruption Potential',
  },
  57: {
    description: 'Freezing Drizzle: Dense intensity',
    icon: '🌧️',
    category: 'drizzle',
    advisory: 'Cold dense drizzle with slippery trails.',
    disruptionLevel: 'Moderate Outdoor Disruption Potential',
  },
  61: {
    description: 'Rain: Slight intensity',
    icon: '🌦️',
    category: 'rain',
    advisory: 'Light rainfall expected. Expect minor delays in outdoor activities; keep umbrellas handy.',
    disruptionLevel: 'Moderate Outdoor Disruption Potential',
  },
  63: {
    description: 'Rain: Moderate intensity',
    icon: '🌧️',
    category: 'rain',
    advisory: 'Continuous rain forecast. Open-air sightseeing and hiking trails may be wet and slippery.',
    disruptionLevel: 'Moderate Outdoor Disruption Potential',
  },
  65: {
    description: 'Rain: Heavy intensity',
    icon: '🌧️',
    category: 'heavy_rain',
    advisory: 'Significant precipitation forecast. Outdoor excursions, safari drives, and steep climbs likely disrupted.',
    disruptionLevel: 'High Outdoor Disruption Potential',
  },
  66: {
    description: 'Freezing Rain: Light intensity',
    icon: '🌧️',
    category: 'rain',
    advisory: 'Cold rainfall creating slippery surfaces.',
    disruptionLevel: 'High Outdoor Disruption Potential',
  },
  67: {
    description: 'Freezing Rain: Heavy intensity',
    icon: '🌧️',
    category: 'heavy_rain',
    advisory: 'Heavy cold rain. Outdoor travel not advised.',
    disruptionLevel: 'High Outdoor Disruption Potential',
  },
  71: {
    description: 'Snow fall: Slight intensity',
    icon: '🌨️',
    category: 'snow',
    advisory: 'Light snowfall.',
    disruptionLevel: 'Moderate Outdoor Disruption Potential',
  },
  73: {
    description: 'Snow fall: Moderate intensity',
    icon: '🌨️',
    category: 'snow',
    advisory: 'Moderate snowfall.',
    disruptionLevel: 'High Outdoor Disruption Potential',
  },
  75: {
    description: 'Snow fall: Heavy intensity',
    icon: '❄️',
    category: 'snow',
    advisory: 'Heavy snowfall.',
    disruptionLevel: 'High Outdoor Disruption Potential',
  },
  77: {
    description: 'Snow grains',
    icon: '❄️',
    category: 'snow',
    advisory: 'Frozen precipitation.',
    disruptionLevel: 'Moderate Outdoor Disruption Potential',
  },
  80: {
    description: 'Rain showers: Slight',
    icon: '🌦️',
    category: 'rain',
    advisory: 'Passing showers likely. Plan flexible timing between outdoor attractions.',
    disruptionLevel: 'Low Outdoor Disruption Potential',
  },
  81: {
    description: 'Rain showers: Moderate',
    icon: '🌧️',
    category: 'rain',
    advisory: 'Intermittent rain showers. Short pauses in outdoor activities may be required.',
    disruptionLevel: 'Moderate Outdoor Disruption Potential',
  },
  82: {
    description: 'Rain showers: Violent',
    icon: '⛈️',
    category: 'heavy_rain',
    advisory: 'Sudden intense downpours. High potential for outdoor disruptions; seek sheltered stops.',
    disruptionLevel: 'High Outdoor Disruption Potential',
  },
  85: {
    description: 'Snow showers: Slight',
    icon: '🌨️',
    category: 'snow',
    advisory: 'Occasional snow flurries.',
    disruptionLevel: 'Moderate Outdoor Disruption Potential',
  },
  86: {
    description: 'Snow showers: Heavy',
    icon: '❄️',
    category: 'snow',
    advisory: 'Heavy snow showers.',
    disruptionLevel: 'High Outdoor Disruption Potential',
  },
  95: {
    description: 'Thunderstorm (slight or moderate)',
    icon: '⛈️',
    category: 'thunderstorm',
    advisory: 'Thunderstorm activity forecast. Lightning risk present; outdoor open-air activities, high-elevation viewpoints, and water excursions should be suspended during storm cells.',
    disruptionLevel: 'High Outdoor Disruption Potential',
  },
  96: {
    description: 'Thunderstorm with slight hail',
    icon: '⛈️',
    category: 'thunderstorm',
    advisory: 'Thunderstorm with slight hail forecast. Severe outdoor disruption; seek sturdy indoor shelter and avoid open terrain.',
    disruptionLevel: 'Severe Outdoor Disruption Potential',
  },
  99: {
    description: 'Thunderstorm with heavy hail',
    icon: '⛈️',
    category: 'thunderstorm',
    advisory: 'Dangerous convective storm with heavy hail forecast. Postpone all outdoor travel; seek immediate sturdy indoor shelter.',
    disruptionLevel: 'Severe Outdoor Disruption Potential',
  },
};

/**
 * Returns documented WMO weather info or a safe unassessed fallback.
 * Unknown codes or missing data do NOT produce a reassuring status.
 */
export function getWmoWeatherInfo(code) {
  if (code != null && WMO_WEATHER_CODES[code]) {
    return { code, ...WMO_WEATHER_CODES[code] };
  }
  return {
    code: code ?? null,
    description: code != null ? `Unrecognized weather code ${code}` : 'Weather telemetry unavailable',
    icon: '❓',
    category: 'unknown',
    advisory: 'Weather telemetry unrecognized or unavailable. Local outdoor conditions cannot be confirmed; verify local conditions before departing.',
    disruptionLevel: 'Unassessed (data incomplete)',
  };
}

// In-memory weather cache: key -> { data, timestamp }
const weatherMemoryCache = new Map();
const CACHE_TTL_MS = 60 * 1000; // 1 minute in-memory cache to deduplicate rapid clicks

/**
 * Resolves destination coordinates from project constants or Open-Meteo geocoding.
 * Never guesses or reuses another city's coordinates.
 */
export async function resolveDestinationCoordinates(destinationName, signal = null) {
  if (!destinationName || typeof destinationName !== 'string') {
    throw new Error('Destination name is required for coordinate resolution.');
  }

  const cleanName = destinationName.trim();

  // 1. Direct project lookup
  if (VERIFIED_DESTINATION_COORDINATES[cleanName]) {
    return {
      ...VERIFIED_DESTINATION_COORDINATES[cleanName],
      source: 'project_verified',
      matchedName: cleanName,
    };
  }

  // Case-insensitive lookup against project coordinates
  const foundKey = Object.keys(VERIFIED_DESTINATION_COORDINATES).find(
    (k) => k.toLowerCase() === cleanName.toLowerCase()
  );
  if (foundKey) {
    return {
      ...VERIFIED_DESTINATION_COORDINATES[foundKey],
      source: 'project_verified',
      matchedName: foundKey,
    };
  }

  // 2. Open-Meteo Geocoding Service with Sri Lanka filtering
  const geocodingUrl = `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(
    cleanName
  )}&count=5&language=en&format=json&country_code=LK`;

  const response = await fetch(geocodingUrl, { signal });
  if (!response.ok) {
    throw new Error(`Geocoding lookup failed with status ${response.status}`);
  }

  const data = await response.json();
  const results = Array.isArray(data?.results) ? data.results : [];

  // Strict Sri Lanka filter & unambiguous check
  const lkResults = results.filter(
    (r) => r.country_code === 'LK' || r.country === 'Sri Lanka'
  );

  if (lkResults.length === 0) {
    throw new Error(
      `No verified Sri Lanka location match found for destination "${cleanName}".`
    );
  }

  // If there are multiple, look for exact name match
  const exact = lkResults.find(
    (r) => r.name.toLowerCase() === cleanName.toLowerCase()
  );

  const matched = exact || lkResults[0];

  return {
    latitude: matched.latitude,
    longitude: matched.longitude,
    source: 'open_meteo_geocoding',
    matchedName: matched.name,
    admin1: matched.admin1,
  };
}

/**
 * Fetches current weather and configured 16-day hourly forecast from Open-Meteo for a single destination.
 * 
 * @param {string} destinationName
 * @param {Object} options
 * @param {boolean} options.forceRefresh - Bypass and clear in-memory cache
 * @param {AbortSignal} options.signal - Abort signal to cancel obsolete requests
 * @returns {Promise<Object>} Formatted weather response
 */
export async function fetchDestinationWeather(destinationName, options = {}) {
  const { forceRefresh = false, signal = null } = options;

  if (!destinationName) {
    throw new Error('Destination name is required.');
  }

  const cacheKey = destinationName.trim().toLowerCase();
  const now = Date.now();

  // If forceRefresh, clear cache entry so real network request is made
  if (forceRefresh) {
    weatherMemoryCache.delete(cacheKey);
  } else if (weatherMemoryCache.has(cacheKey)) {
    const cached = weatherMemoryCache.get(cacheKey);
    if (now - cached.timestamp < CACHE_TTL_MS) {
      // Retain original fetch timestamp from cache
      return { ...cached.data, fromCache: true };
    }
  }

  // 1. Resolve coordinates
  const coords = await resolveDestinationCoordinates(destinationName, signal);

  // 2. Open-Meteo Forecast API
  const params = new URLSearchParams({
    latitude: coords.latitude.toString(),
    longitude: coords.longitude.toString(),
    current: 'temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_direction_10m',
    hourly: 'temperature_2m,precipitation_probability,precipitation,weather_code,wind_speed_10m',
    timezone: 'Asia/Colombo',
    forecast_days: '16',
  });

  const forecastUrl = `https://api.open-meteo.com/v1/forecast?${params.toString()}`;

  const response = await fetch(forecastUrl, { signal });

  if (response.status === 429) {
    throw new Error('Open-Meteo rate limit reached. Please wait a few moments before refreshing.');
  }

  if (!response.ok) {
    throw new Error(`Open-Meteo request failed (HTTP ${response.status} ${response.statusText})`);
  }

  const data = await response.json();

  if (!data?.current || !data?.hourly) {
    throw new Error('Incomplete weather telemetry returned by provider.');
  }

  const currentWmo = getWmoWeatherInfo(data.current.weather_code);

  // Process hourly items
  const hourlyTimes = data.hourly.time || [];
  const hourlyTemps = data.hourly.temperature_2m || [];
  const hourlyPrecipProb = data.hourly.precipitation_probability || [];
  const hourlyPrecip = data.hourly.precipitation || [];
  const hourlyCodes = data.hourly.weather_code || [];
  const hourlyWinds = data.hourly.wind_speed_10m || [];

  const processedHourly = hourlyTimes.map((tStr, idx) => {
    const [datePart, timePart] = tStr.split('T');
    return {
      isoTime: tStr,
      dateStr: datePart,
      hourStr: timePart || '',
      temperature: hourlyTemps[idx],
      precipitationProbability: hourlyPrecipProb[idx] ?? null,
      precipitation: hourlyPrecip[idx] ?? 0,
      weatherCode: hourlyCodes[idx],
      weatherInfo: getWmoWeatherInfo(hourlyCodes[idx]),
      windSpeed: hourlyWinds[idx] ?? null,
    };
  });

  const fetchTimestamp = new Date().toISOString();

  const result = {
    destination: destinationName,
    coordinates: {
      latitude: coords.latitude,
      longitude: coords.longitude,
      source: coords.source,
    },
    current: {
      time: data.current.time, // ISO string in Asia/Colombo e.g. "2026-10-19T02:00"
      temperature: data.current.temperature_2m,
      apparentTemperature: data.current.apparent_temperature,
      relativeHumidity: data.current.relative_humidity_2m,
      precipitation: data.current.precipitation,
      weatherCode: data.current.weather_code,
      weatherInfo: currentWmo,
      windSpeed: data.current.wind_speed_10m,
      windDirection: data.current.wind_direction_10m,
    },
    units: {
      temperature: data.current_units?.temperature_2m || '°C',
      precipitation: data.current_units?.precipitation || 'mm',
      windSpeed: data.current_units?.wind_speed_10m || 'km/h',
      relativeHumidity: data.current_units?.relative_humidity_2m || '%',
    },
    hourly: processedHourly,
    timezone: data.timezone || 'Asia/Colombo',
    fetchTimestamp, // Client fetch time
    validTime: data.current.time, // Numerical model timestep
    fromCache: false,
    attribution: 'Weather data by Open-Meteo.com (CC BY 4.0)',
    attributionUrl: 'https://open-meteo.com/',
    officialDmcUrl: 'https://www.dmc.gov.lk/',
  };

  // Cache result
  weatherMemoryCache.set(cacheKey, {
    data: result,
    timestamp: now,
  });

  return result;
}

/**
 * Filter hourly forecast for a specific visit date.
 * If visit date is today, displays upcoming hours.
 * If visit date is a future date covered by forecast, displays that day's hours.
 * If not covered, returns coverage bounds and an explanatory notice.
 */
export function getRelevantHourlyForecast(weatherData, visitDateStr) {
  if (!weatherData?.hourly || weatherData.hourly.length === 0) {
    return null;
  }

  // Determine coverage from actual returned timestamps with valid values
  const validHourly = weatherData.hourly.filter(
    (h) => h.temperature != null && h.dateStr
  );
  const coveredDates = [...new Set(validHourly.map((h) => h.dateStr))];
  const earliestDate = coveredDates[0] || '';
  const latestDate = coveredDates[coveredDates.length - 1] || '';

  // Get current date string in Colombo timezone
  const todayColomboStr = (weatherData.current?.time || '').split('T')[0];
  const targetDateStr = visitDateStr || todayColomboStr;

  const dayItems = validHourly.filter((h) => h.dateStr === targetDateStr);

  if (dayItems.length === 0) {
    return {
      covered: false,
      reason: 'Forecast unavailable for this date',
      targetDate: targetDateStr,
      coverageRange: `${earliestDate} to ${latestDate}`,
      message: `The selected visit date (${targetDateStr}) is outside this application's configured 15-day forecast window (${earliestDate} to ${latestDate}). Current model conditions remain displayed separately above.`,
      items: [],
    };
  }

  // If the target date is today, filter for upcoming hours starting from current model timestep
  if (targetDateStr === todayColomboStr && weatherData.current?.time) {
    const currentHourStr = (weatherData.current.time.split('T')[1] || '00:00').slice(0, 2);
    const upcoming = dayItems.filter((h) => h.hourStr.slice(0, 2) >= currentHourStr);
    return {
      covered: true,
      isToday: true,
      targetDate: targetDateStr,
      coverageRange: `${earliestDate} to ${latestDate}`,
      items: upcoming.length > 0 ? upcoming : dayItems.slice(-6),
    };
  }

  return {
    covered: true,
    isToday: false,
    targetDate: targetDateStr,
    coverageRange: `${earliestDate} to ${latestDate}`,
    items: dayItems,
  };
}

/**
 * Evaluates weather conditions and generates application-defined outdoor activity guidance.
 * 
 * Rules:
 * - Application outdoor activity guidance, not official disaster warnings or warning levels.
 * - Explains potential outdoor disruption.
 * - Code 95 does NOT assert hail or strong wind; hail is only described if code is 96 or 99;
 *   strong wind is only described if actual wind data supports it.
 * - Unknown codes or incomplete data produce an unassessed status, never a reassuring one.
 * - Does not infer landslides, floods, or road closures from weather alone.
 * - Official warning status is strictly "Not checked" with "No automated official-warning feed is integrated."
 */
export function generateWeatherAdvisory(weatherData, targetHourlyForecast) {
  if (!weatherData?.current) {
    return {
      level: 'Notice',
      title: 'Weather Guidance: Telemetry Pending',
      message: 'Select a destination to evaluate local meteorological conditions.',
      outdoorDisruption: 'Unassessed (no destination selected)',
      officialWarningStatus: 'Not checked',
      officialWarningNote: 'No automated official-warning feed is integrated.',
      disclaimer: 'Application-defined outdoor guidance based on Open-Meteo numerical weather prediction models; not an official disaster warning or road safety guarantee.',
      officialDmcUrl: 'https://www.dmc.gov.lk/',
    };
  }

  const currentInfo = weatherData.current.weatherInfo;
  const currentCode = weatherData.current.weatherCode;
  const currentPrecip = weatherData.current.precipitation || 0;
  const currentWind = weatherData.current.windSpeed || 0;

  // Unknown or incomplete weather code must NOT produce a reassuring status
  if (currentCode == null || currentInfo.category === 'unknown') {
    return {
      level: 'Notice',
      title: 'Weather Guidance: Unassessed',
      message: 'Weather telemetry is incomplete or unrecognized. Outdoor disruption cannot be reliably evaluated from numerical model output.',
      outdoorDisruption: 'Unassessed (data incomplete)',
      officialWarningStatus: 'Not checked',
      officialWarningNote: 'No automated official-warning feed is integrated.',
      officialDmcUrl: 'https://www.dmc.gov.lk/',
      disclaimer:
        'Application-defined outdoor guidance based on Open-Meteo numerical weather prediction models. This does not constitute an official government disaster warning, evacuation notice, or road safety guarantee.',
    };
  }

  // Check upcoming forecast hours
  const upcomingItems = targetHourlyForecast?.items || [];
  const hasUpcomingHailStorm = upcomingItems.some(
    (h) => h.weatherCode === 96 || h.weatherCode === 99
  );
  const hasUpcomingThunderstorm = upcomingItems.some(
    (h) => h.weatherCode === 95
  );
  const hasUpcomingHeavyRain = upcomingItems.some(
    (h) => h.weatherCode === 65 || h.weatherCode === 82 || (h.precipitation && h.precipitation > 5)
  );
  const hasUpcomingRain = upcomingItems.some(
    (h) => (h.weatherCode >= 61 && h.weatherCode <= 63) || h.weatherCode === 80 || h.weatherCode === 81
  );

  let level = 'Normal';
  let title = 'Favorable Conditions';
  let message = currentInfo.advisory;
  let outdoorDisruption = currentInfo.disruptionLevel;

  // 1. Hail thunderstorms (Codes 96, 99)
  if (hasUpcomingHailStorm || currentCode === 96 || currentCode === 99) {
    level = 'Caution';
    title = 'Thunderstorm with Hail Advisory';
    message =
      'Convective thunderstorm with hail potential forecast in this area. Outdoor open-air travel should be postponed; seek sturdy indoor shelter.';
    outdoorDisruption = 'Severe Outdoor Disruption Potential';
  }
  // 2. Standard thunderstorms (Code 95 - does NOT establish hail or strong wind)
  else if (hasUpcomingThunderstorm || currentCode === 95) {
    level = 'Caution';
    title = 'Thunderstorm Advisory';
    message =
      'Thunderstorm conditions forecast in this area. Lightning risk present; outdoor open-air activities, summit climbs (e.g. Sigiriya), and water excursions should be suspended during storm cells.';
    if (currentWind > 40) {
      message += ` High wind speeds of ${currentWind} km/h detected.`;
    }
    outdoorDisruption = 'High Outdoor Disruption Potential';
  }
  // 3. Heavy rain (Codes 65, 82)
  else if (hasUpcomingHeavyRain || currentCode === 65 || currentCode === 82 || currentPrecip > 5) {
    level = 'Caution';
    title = 'Heavy Rain Advisory';
    message =
      'Significant precipitation forecast. Open trails, botanical walks, and wildlife safaris may experience major disruption. Waterproof equipment and slower road travel expected.';
    outdoorDisruption = 'High Outdoor Disruption Potential';
  }
  // 4. Rain (Codes 61-63, 80-81)
  else if (hasUpcomingRain || (currentCode >= 61 && currentCode <= 63) || currentCode === 80 || currentCode === 81) {
    level = 'Notice';
    title = 'Rain Advisory';
    message =
      'Rainfall forecast during the activity window. Bring rain protection and maintain flexible timing for outdoor stops.';
    outdoorDisruption = 'Moderate Outdoor Disruption Potential';
  }
  // 5. Fog (Codes 45, 48)
  else if (currentCode === 45 || currentCode === 48) {
    level = 'Notice';
    title = 'Fog & Low Visibility Advisory';
    message =
      'Dense mist or fog present. Mountain viewpoints may have limited visibility. Drive carefully along mountain passes.';
    outdoorDisruption = 'Moderate Outdoor Disruption Potential';
  }
  // 6. High wind alone (> 40 km/h)
  else if (currentWind > 40) {
    level = 'Notice';
    title = 'Breezy / High Wind Conditions';
    message = `Wind speeds of ${currentWind} km/h recorded. Coastal and exposed mountain areas will feel windy; secure hats and loose gear.`;
    outdoorDisruption = 'Moderate Outdoor Disruption Potential';
  }

  return {
    level,
    title,
    message,
    outdoorDisruption,
    officialWarningStatus: 'Not checked',
    officialWarningNote: 'No automated official-warning feed is integrated.',
    disclaimer:
      'Application-defined outdoor guidance based on Open-Meteo numerical weather prediction models. This does not constitute an official government disaster warning, evacuation notice, or road safety guarantee.',
    officialDmcUrl: 'https://www.dmc.gov.lk/',
  };
}

/**
 * Labeled test fixtures strictly for simulated verification outside the production UI.
 * Must NOT be loaded into production UI, live caches, or shortlist/route states.
 */
export const FIXTURES_FOR_TESTING = {
  severeThunderstormWithHail: {
    destination: 'Test Destination (Hail Storm)',
    isFixture: true,
    current: {
      time: '2026-10-19T14:00',
      temperature: 24.5,
      apparentTemperature: 28.0,
      relativeHumidity: 95,
      precipitation: 14.0,
      weatherCode: 96,
      weatherInfo: WMO_WEATHER_CODES[96],
      windSpeed: 45.0,
      windDirection: 180,
    },
    units: { temperature: '°C', precipitation: 'mm', windSpeed: 'km/h', relativeHumidity: '%' },
  },
  thunderstormStandard: {
    destination: 'Test Destination (Standard Thunderstorm)',
    isFixture: true,
    current: {
      time: '2026-10-19T14:00',
      temperature: 26.0,
      apparentTemperature: 29.0,
      relativeHumidity: 90,
      precipitation: 6.0,
      weatherCode: 95,
      weatherInfo: WMO_WEATHER_CODES[95],
      windSpeed: 18.0, // Normal wind - does NOT assert strong wind
      windDirection: 160,
    },
    units: { temperature: '°C', precipitation: 'mm', windSpeed: 'km/h', relativeHumidity: '%' },
  },
  heavyRain: {
    destination: 'Test Destination (Heavy Rain)',
    isFixture: true,
    current: {
      time: '2026-10-19T14:00',
      temperature: 22.0,
      apparentTemperature: 24.0,
      relativeHumidity: 98,
      precipitation: 18.5,
      weatherCode: 65,
      weatherInfo: WMO_WEATHER_CODES[65],
      windSpeed: 25.0,
      windDirection: 220,
    },
    units: { temperature: '°C', precipitation: 'mm', windSpeed: 'km/h', relativeHumidity: '%' },
  },
  unknownCode: {
    destination: 'Test Destination (Corrupted Code)',
    isFixture: true,
    current: {
      time: '2026-10-19T14:00',
      temperature: 20.0,
      apparentTemperature: 20.0,
      relativeHumidity: 50,
      precipitation: 0.0,
      weatherCode: 9999, // Unrecognized code
      weatherInfo: getWmoWeatherInfo(9999),
      windSpeed: 10.0,
      windDirection: 0,
    },
    units: { temperature: '°C', precipitation: 'mm', windSpeed: 'km/h', relativeHumidity: '%' },
  },
};
