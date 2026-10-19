import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { getRecommendations, getAutomaticWeatherAndCrowd, calculateCrowdFromDate } from './api.js';
import {
  fetchDestinationWeather,
  getRelevantHourlyForecast,
  generateWeatherAdvisory,
  getWmoWeatherInfo,
  detectDestinationFromQuery,
} from './weatherService.js';

const formatDateStr = (d) => {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

// Open-Meteo is queried with forecast_days=16 (today + 15 days)
const WEATHER_FORECAST_DAYS_AHEAD = 15;

const getTomorrowDateStr = () => {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  return formatDateStr(tomorrow);
};

const getMaxDateStr = () => {
  const maxDate = new Date();
  maxDate.setDate(maxDate.getDate() + 1);
  maxDate.setMonth(maxDate.getMonth() + 2);
  return formatDateStr(maxDate);
};

// Verified activity categories from backend data contract
export const VERIFIED_INTEREST_OPTIONS = [
  { id: 'nature', label: 'Nature', icon: '🌲' },
  { id: 'beach', label: 'Beach', icon: '🏖️' },
  { id: 'hiking', label: 'Hiking', icon: '🥾' },
  { id: 'cultural', label: 'Culture & Heritage', icon: '🏛️' },
  { id: 'wildlife', label: 'Wildlife', icon: '🐘' },
  { id: 'adventure', label: 'Adventure', icon: '🧗' },
  { id: 'relaxing', label: 'Relaxing', icon: '🧘' },
];

/**
 * Documented Crowd Precedence:
 * 1. Primary: Numeric `item.crowd` (continuous regression metric). Lower is better.
 * 2. Secondary fallback: `item.crowd_label` or `item.crowd_safety?.crowd_level`:
 *    'low' (100) < 'moderate' (150) < 'high' (200) < 'very high' (250).
 * 3. Missing crowd data: Treated as Infinity (placed last in sorting; rejected in strict filtering).
 * 4. Tie-breaking: Original API response index preserved.
 * 5. Strict threshold: < 110 based on backend contract (classify_crowd_level threshold in backend).
 */
export const getComparableCrowdValue = (item) => {
  if (typeof item?.crowd === 'number' && !isNaN(item.crowd)) {
    return item.crowd;
  }
  const label = (item?.crowd_label || item?.crowd_safety?.crowd_level || '').toLowerCase().trim();
  if (label === 'low') return 100;
  if (label === 'moderate') return 150;
  if (label === 'high') return 200;
  if (label === 'very high') return 250;
  return Infinity;
};

export const isLowCrowdStrict = (item) => {
  if (item?.crowd_label) {
    return item.crowd_label.toLowerCase().trim() === 'low';
  }
  if (item?.crowd_safety?.crowd_level) {
    return item.crowd_safety.crowd_level.toLowerCase().trim() === 'low';
  }
  if (typeof item?.crowd === 'number' && !isNaN(item.crowd)) {
    return item.crowd < 110;
  }
  return false;
};

export default function DestinationRecommendations({ onBack }) {
  const tomorrowStr = getTomorrowDateStr();
  const maxDateStr = getMaxDateStr();

  // Search parameters
  const [userPrefText, setUserPrefText] = useState('');
  const [plannedDate, setPlannedDate] = useState(tomorrowStr);
  const origin = 'Colombo';
  const [days, setDays] = useState(3);
  const [transportMode, setTransportMode] = useState('car');

  // Raw API state (remains unchanged after response arrives)
  const [rawRecommendations, setRawRecommendations] = useState([]);
  const [routeRecommendations, setRouteRecommendations] = useState([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [loadingRecs, setLoadingRecs] = useState(false);
  const [isLiveApi, setIsLiveApi] = useState(false);
  const [apiError, setApiError] = useState(null);
  const [locationWarning, setLocationWarning] = useState(null);

  // Client-side Filter & Sort Controls
  const [selectedInterests, setSelectedInterests] = useState([]);
  const [preferLowerCrowds, setPreferLowerCrowds] = useState(false); // Stable sort toggle
  const [filterLowCrowdOnly, setFilterLowCrowdOnly] = useState(false); // Strict filter toggle
  const [weatherFilter, setWeatherFilter] = useState('all'); // 'all' | 'good_excellent' | 'excellent'
  const [excludedPlaces, setExcludedPlaces] = useState([]);
  const [showShortlistOnly, setShowShortlistOnly] = useState(false);
  const [isFilterPanelOpen, setIsFilterPanelOpen] = useState(false);

  // Shortlist State (reconciled on new search, stable by place name)
  const [shortlist, setShortlist] = useState([]);

  // Comparison State (max 3 places)
  const [comparisonPlaces, setComparisonPlaces] = useState([]);
  const [isComparisonOpen, setIsComparisonOpen] = useState(false);
  const [expandedActivitiesPlace, setExpandedActivitiesPlace] = useState(null);

  // Live Open-Meteo Weather Advisory State
  const [selectedWeatherDestination, setSelectedWeatherDestination] = useState(null);
  const [queryDestinationStatus, setQueryDestinationStatus] = useState(null);
  const [weatherData, setWeatherData] = useState(null);
  const [weatherLoading, setWeatherLoading] = useState(false);
  const [weatherError, setWeatherError] = useState(null);
  const [weatherIsStale, setWeatherIsStale] = useState(false);
  const [weatherLastSuccessTime, setWeatherLastSuccessTime] = useState(null);
  const [manualRefreshCooldown, setManualRefreshCooldown] = useState(0);

  const abortControllerRef = useRef(null);
  const activeDestRef = useRef(null);
  const lastFetchTimeRef = useRef(0);
  const lastManualRefreshClickRef = useRef(0);

  // Load weather for a given destination
  const loadWeather = useCallback(async (destName, force = false) => {
    if (!destName) return;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;
    activeDestRef.current = destName;

    setWeatherLoading(true);
    setWeatherError(null);

    try {
      const res = await fetchDestinationWeather(destName, {
        forceRefresh: force,
        signal: controller.signal,
      });

      // Guard: discard response if destination changed while request was in-flight
      if (activeDestRef.current !== destName) return;

      setWeatherData(res);
      setWeatherIsStale(false);

      // Update lastSuccessfulFetch only after a successful request.
      // Cache reads retain their original fetch timestamp; fresh fetches use new timestamp.
      if (res.fromCache && res.fetchTimestamp) {
        setWeatherLastSuccessTime(new Date(res.fetchTimestamp).toLocaleTimeString());
      } else {
        setWeatherLastSuccessTime(new Date().toLocaleTimeString());
      }

      lastFetchTimeRef.current = Date.now();
      setWeatherLoading(false);
    } catch (err) {
      if (err.name === 'AbortError') return;
      if (activeDestRef.current !== destName) return;

      console.warn(`Weather fetch failed for ${destName}:`, err);
      setWeatherError(err.message || 'Unable to fetch weather conditions');
      // On failure, visibly mark retained data as stale without updating lastSuccessTime
      setWeatherIsStale(true);
      setWeatherLoading(false);
    }
  }, []);

  // Manual refresh handler: bypasses response cache with rate-limit cooldown
  const handleManualRefresh = useCallback(() => {
    if (!selectedWeatherDestination || weatherLoading) return;
    const now = Date.now();
    const COOLDOWN_MS = 5000;
    if (now - lastManualRefreshClickRef.current < COOLDOWN_MS) {
      return;
    }
    lastManualRefreshClickRef.current = now;
    setManualRefreshCooldown(5);
    loadWeather(selectedWeatherDestination, true);
  }, [selectedWeatherDestination, weatherLoading, loadWeather]);

  // Cooldown countdown timer for manual refresh button
  useEffect(() => {
    if (manualRefreshCooldown <= 0) return;
    const timer = setInterval(() => {
      setManualRefreshCooldown((prev) => (prev > 1 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [manualRefreshCooldown]);

  // Fetch weather on destination selection
  useEffect(() => {
    if (selectedWeatherDestination) {
      loadWeather(selectedWeatherDestination, false);
    }
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [selectedWeatherDestination, loadWeather]);

  // 15-minute auto-refresh while page is visible
  useEffect(() => {
    const REFRESH_INTERVAL_MS = 15 * 60 * 1000;

    const intervalId = setInterval(() => {
      if (document.visibilityState === 'visible' && activeDestRef.current) {
        loadWeather(activeDestRef.current, true);
      }
    }, REFRESH_INTERVAL_MS);

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && activeDestRef.current) {
        const timeSinceLast = Date.now() - lastFetchTimeRef.current;
        if (timeSinceLast >= REFRESH_INTERVAL_MS) {
          loadWeather(activeDestRef.current, true);
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      clearInterval(intervalId);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [loadWeather]);

  // Prevent showing previous city's data under new city's heading
  const isMatchingDestData = Boolean(
    weatherData && weatherData.destination === selectedWeatherDestination
  );

  // Active weather data strictly matches the selected destination
  const activeWeatherData = useMemo(() => {
    return isMatchingDestData ? weatherData : null;
  }, [isMatchingDestData, weatherData]);

  // Hourly forecast evaluated for selected visit date (or today upcoming)
  // Automatically guarded against stale forecast when plannedDate changes
  const relevantHourly = useMemo(() => {
    if (!activeWeatherData) return null;
    return getRelevantHourlyForecast(activeWeatherData, plannedDate);
  }, [activeWeatherData, plannedDate]);

  // Application-defined outdoor activity guidance generated from provider's documented WMO codes
  const activeAdvisory = useMemo(() => {
    return generateWeatherAdvisory(activeWeatherData, relevantHourly);
  }, [activeWeatherData, relevantHourly]);

  // Fetch recommendations from AWS API
  const fetchRecommendationsData = async (
    prefText = userPrefText,
    dateVal = plannedDate,
    origVal = origin,
    daysVal = days,
    modeVal = transportMode
  ) => {
    setLoadingRecs(true);
    setHasSearched(true);
    setApiError(null);
    setLocationWarning(null);

    const res = await getRecommendations(prefText, {
      plannedDate: dateVal,
      origin: origVal,
      days: Number(daysVal) || 3,
      transport_mode: modeVal,
    });

    if (res?.errorDetail && (!res?.recommendations || res.recommendations.length === 0)) {
      setApiError(res.errorDetail);
      setRawRecommendations([]);
      setRouteRecommendations([]);
      setIsLiveApi(false);
      setLoadingRecs(false);
      return;
    }

    // Place not in Sri Lanka (or misspelled): show the warning instead of any results
    if (res?.locationWarning) {
      setLocationWarning(res.locationWarning);
      setRawRecommendations([]);
      setRouteRecommendations([]);
      setSelectedWeatherDestination(null);
      setQueryDestinationStatus(null);
      setIsLiveApi(!!res?.isLive);
      setLoadingRecs(false);
      return;
    }

    const recs = res?.recommendations || [];
    const routes = res?.route_recommendations || [];

    // Store pristine response
    setRawRecommendations(recs);
    setRouteRecommendations(routes);
    setIsLiveApi(!!res?.isLive);
    setApiError(null);

    // Automatic destination detection from submitted query
    const detection = detectDestinationFromQuery(prefText);
    setQueryDestinationStatus(detection);

    // Fallback: a recommended place explicitly named in the query (covers places outside the alias list)
    const lowerPref = (prefText || '').toLowerCase();
    const namedRec = recs.find((r) => r.place && lowerPref.includes(r.place.toLowerCase()));

    if (detection.isUnambiguous && detection.detected) {
      // Unambiguous query (e.g. Kandy) automatically selected
      setSelectedWeatherDestination(detection.detected);
    } else if (detection.reason === 'no_destination_specified' && namedRec) {
      setSelectedWeatherDestination(namedRec.place);
    } else if (recs.length > 0) {
      // Ambiguous or multi-destination query: retain current selection if valid or default to top recommendation
      setSelectedWeatherDestination((prev) =>
        prev && recs.some((r) => r.place === prev) ? prev : recs[0].place
      );
    }

    // Reconcile shortlist: remove stale places not present in new response
    setShortlist((prev) => prev.filter((pName) => recs.some((r) => r.place === pName)));
    // Reconcile comparison: remove stale places not present in new response
    setComparisonPlaces((prev) => prev.filter((pName) => recs.some((r) => r.place === pName)));

    setLoadingRecs(false);
  };

  // Image resolver
  const getPlaceImage = (pName, providedImg) => {
    if (providedImg && !providedImg.includes('undefined')) return providedImg;
    const clean = (pName || '').toLowerCase().trim();
    if (clean.includes('galle')) return '/images/galle.png';
    if (clean.includes('sigiriya')) return '/images/sigiriya.png';
    if (clean.includes('nuwara')) return '/images/nuwara_eliya.png';
    if (
      clean.includes('mirissa') ||
      clean.includes('bentota') ||
      clean.includes('arugam') ||
      clean.includes('trincomalee') ||
      clean.includes('hikkaduwa')
    ) {
      return '/images/mirissa.png';
    }
    return '/images/ella.png';
  };

  // Derived filtered & sorted recommendations (pure derived state, rawRecommendations unchanged)
  const displayedRecommendations = useMemo(() => {
    if (!rawRecommendations || rawRecommendations.length === 0) return [];

    // 1. Tag with original API index to guarantee stable sort on ties
    const indexed = rawRecommendations.map((item, idx) => ({ ...item, _apiIndex: idx }));

    // 2. Filter phase
    const filtered = indexed.filter((item) => {
      // Exclude destinations filter
      if (excludedPlaces.includes(item.place)) {
        return false;
      }

      // Shortlist only filter
      if (showShortlistOnly && !shortlist.includes(item.place)) {
        return false;
      }

      // Strict "Low crowd only" filter
      if (filterLowCrowdOnly && !isLowCrowdStrict(item)) {
        return false;
      }

      // Weather filtering (using verified condition; do not treat missing as good weather)
      if (weatherFilter === 'good_excellent') {
        const cond = (item.weather || item.weather_suitability?.condition || '').toLowerCase().trim();
        if (cond !== 'good' && cond !== 'excellent') return false;
      } else if (weatherFilter === 'excellent') {
        const cond = (item.weather || item.weather_suitability?.condition || '').toLowerCase().trim();
        if (cond !== 'excellent') return false;
      }

      // Activity-interest filtering
      if (selectedInterests.length > 0) {
        const acts = item.activity_recommendations?.activities || [];
        const allCats = new Set();
        acts.forEach((a) => (a.categories || []).forEach((c) => allCats.add(c.toLowerCase().trim())));
        if (item.activity_recommendations?.top_activity?.category) {
          allCats.add(item.activity_recommendations.top_activity.category.toLowerCase().trim());
        }
        (item.preference_match?.matched || []).forEach((m) => allCats.add(m.toLowerCase().trim()));

        const matchesAny = selectedInterests.some((sel) => {
          if (sel === 'cultural') {
            return (
              allCats.has('cultural') ||
              allCats.has('heritage') ||
              allCats.has('temple') ||
              allCats.has('history')
            );
          }
          return allCats.has(sel);
        });

        if (!matchesAny) return false;
      }

      return true;
    });

    // 3. Sorting phase: "Prefer lower crowds" is a stable sort that prioritizes lower crowds
    // while retaining all results that pass the other active filters
    if (preferLowerCrowds) {
      return [...filtered].sort((a, b) => {
        const valA = getComparableCrowdValue(a);
        const valB = getComparableCrowdValue(b);
        if (valA !== valB) {
          return valA - valB;
        }
        return a._apiIndex - b._apiIndex; // Preserves original API order for ties
      });
    }

    return filtered;
  }, [
    rawRecommendations,
    excludedPlaces,
    showShortlistOnly,
    shortlist,
    filterLowCrowdOnly,
    preferLowerCrowds,
    weatherFilter,
    selectedInterests,
  ]);

  // Reset all filters restoring original API sequence
  const handleClearFilters = () => {
    setSelectedInterests([]);
    setPreferLowerCrowds(false);
    setFilterLowCrowdOnly(false);
    setWeatherFilter('all');
    setExcludedPlaces([]);
    setShowShortlistOnly(false);
  };

  const hasActiveFilters =
    selectedInterests.length > 0 ||
    preferLowerCrowds ||
    filterLowCrowdOnly ||
    weatherFilter !== 'all' ||
    excludedPlaces.length > 0 ||
    showShortlistOnly;

  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (selectedInterests.length > 0) count += selectedInterests.length;
    if (preferLowerCrowds) count += 1;
    if (filterLowCrowdOnly) count += 1;
    if (weatherFilter !== 'all') count += 1;
    if (showShortlistOnly) count += 1;
    if (excludedPlaces.length > 0) count += excludedPlaces.length;
    return count;
  }, [selectedInterests, preferLowerCrowds, filterLowCrowdOnly, weatherFilter, showShortlistOnly, excludedPlaces]);

  // Shortlist toggler
  const toggleShortlist = (placeName) => {
    setShortlist((prev) =>
      prev.includes(placeName) ? prev.filter((p) => p !== placeName) : [...prev, placeName]
    );
  };

  // Exclude destination handler
  const handleExcludePlace = (placeName) => {
    if (!excludedPlaces.includes(placeName)) {
      setExcludedPlaces((prev) => [...prev, placeName]);
    }
  };

  const handleRestorePlace = (placeName) => {
    setExcludedPlaces((prev) => prev.filter((p) => p !== placeName));
  };

  // Comparison toggle (up to 3)
  const toggleComparison = (placeName) => {
    setComparisonPlaces((prev) => {
      if (prev.includes(placeName)) {
        return prev.filter((p) => p !== placeName);
      }
      if (prev.length >= 3) {
        alert('You can compare a maximum of 3 destinations at a time.');
        return prev;
      }
      return [...prev, placeName];
    });
  };

  const clearComparison = () => {
    setComparisonPlaces([]);
    setIsComparisonOpen(false);
  };

  // Pre-computed AI route from backend
  const recommendedRoute =
    routeRecommendations && routeRecommendations.length > 0 ? routeRecommendations[0] : null;

  // Compact per-stop weather for the recommended route (origin excluded)
  const routeStops = useMemo(
    () => (recommendedRoute?.route || []).filter((stop) => stop && stop !== origin),
    [recommendedRoute]
  );
  const [routeStopWeather, setRouteStopWeather] = useState({});

  useEffect(() => {
    if (routeStops.length === 0) {
      setRouteStopWeather({});
      return;
    }
    const controller = new AbortController();
    setRouteStopWeather({});
    routeStops.forEach((stop) => {
      fetchDestinationWeather(stop, { signal: controller.signal })
        .then((res) => {
          setRouteStopWeather((prev) => ({ ...prev, [stop]: { data: res } }));
        })
        .catch((err) => {
          if (err.name === 'AbortError') return;
          setRouteStopWeather((prev) => ({ ...prev, [stop]: { error: true } }));
        });
    });
    return () => controller.abort();
  }, [routeStops]);

  // Per-stop forecast for the day that stop is visited (trip start + day offset)
  const routeStopForecasts = useMemo(() => {
    const dailyPlan = recommendedRoute?.daily_plan || [];
    return routeStops.map((stop, idx) => {
      // Day the stop is reached: first daily plan leg ending at this stop, else its position
      const leg = dailyPlan.find((dp) => {
        const parts = String(dp.route || '').split('→').map((s) => s.trim());
        return parts[parts.length - 1] === stop;
      });
      const day = Number(leg?.day) || idx + 1;
      const [y, m, d] = plannedDate.split('-').map(Number);
      const visitDate = formatDateStr(new Date(y, m - 1, d + day - 1));

      const entry = routeStopWeather[stop];
      const base = { stop, day, visitDate };
      if (!entry) return { ...base, status: 'loading' };
      if (entry.error) return { ...base, status: 'error' };

      const forecast = getRelevantHourlyForecast(entry.data, visitDate);
      if (!forecast?.covered || forecast.items.length === 0) return { ...base, status: 'out_of_range' };

      // Summarise daytime hours: worst (highest) WMO code and max temperature
      const daytime = forecast.items.filter((h) => {
        const hr = Number(h.hourStr.slice(0, 2));
        return hr >= 6 && hr <= 18;
      });
      const hours = daytime.length > 0 ? daytime : forecast.items;
      const worstCode = Math.max(...hours.map((h) => h.weatherCode ?? -1));
      const info = getWmoWeatherInfo(worstCode >= 0 ? worstCode : null);
      const temps = hours.map((h) => h.temperature).filter((t) => t != null);
      return {
        ...base,
        status: 'ok',
        icon: info.icon,
        description: info.description,
        maxTemp: temps.length > 0 ? Math.max(...temps) : null,
      };
    });
  }, [routeStops, routeStopWeather, recommendedRoute, plannedDate]);

  // Destinations selected for comparison modal
  const comparedDestinationObjects = useMemo(() => {
    return comparisonPlaces
      .map((pName) => rawRecommendations.find((r) => r.place === pName))
      .filter(Boolean);
  }, [comparisonPlaces, rawRecommendations]);

  return (
    <div className="events-travel-planner" style={styles.container}>
      <style>{`
        .events-travel-planner {
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
          color: #0f172a;
          background: #f8fafc;
          min-height: 100vh;
        }
        .events-travel-planner * {
          box-sizing: border-box;
        }
        @media (prefers-reduced-motion: reduce) {
          .events-travel-planner,
          .events-travel-planner * {
            animation-duration: 0.01ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.01ms !important;
            scroll-behavior: auto !important;
          }
        }
        .trip-form-grid {
          display: grid;
          grid-template-columns: 2fr 1fr 1fr 1fr auto;
          gap: 12px;
          align-items: flex-end;
        }
        @media (max-width: 960px) {
          .trip-form-grid {
            grid-template-columns: 1fr 1fr;
          }
          .trip-form-grid > div:first-child {
            grid-column: 1 / -1;
          }
          .trip-form-grid > div:last-child {
            grid-column: 1 / -1;
          }
        }
        @media (max-width: 600px) {
          .trip-form-grid {
            grid-template-columns: 1fr;
          }
          .destination-card {
            flex-direction: column !important;
          }
          .destination-card > div:first-child {
            width: 100% !important;
            height: 140px !important;
          }
        }
        .events-travel-planner button:focus-visible,
        .events-travel-planner select:focus-visible,
        .events-travel-planner input:focus-visible,
        .events-travel-planner summary:focus-visible {
          outline: 2px solid #2563eb !important;
          outline-offset: 2px !important;
        }
        details summary {
          cursor: pointer;
          user-select: none;
        }
        details summary::-webkit-details-marker {
          display: none;
        }
        details[open] > summary {
          color: #1d4ed8;
          font-weight: 700;
        }
      `}</style>

      {/* ── Top Navigation Header ── */}
      <header style={styles.exploreNavHeader}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <button onClick={onBack} style={styles.backNavBtn} aria-label="Go back to Home">
            ← Back
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ ...styles.cardIconBadge, width: 34, height: 34, background: '#2563eb' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2.2">
                <path d="M12 2a8 8 0 0 0-8 8c0 5.25 8 12 8 12s8-6.75 8-12a8 8 0 0 0-8-8z" />
                <circle cx="12" cy="10" r="3" />
              </svg>
            </div>
            <span style={{ fontSize: 16, fontWeight: 700, color: '#0f172a' }}>
              Events & Travel Planner
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          {shortlist.length > 0 && (
            <button
              onClick={() => setShowShortlistOnly(!showShortlistOnly)}
              style={{
                ...styles.controlChipBtn,
                background: showShortlistOnly ? '#fef3c7' : '#ffffff',
                borderColor: showShortlistOnly ? '#f59e0b' : '#cbd5e1',
                color: showShortlistOnly ? '#b45309' : '#334155',
              }}
              title="Filter list to show your shortlisted destinations"
            >
              ★ Shortlist ({shortlist.length})
            </button>
          )}

          {(() => {
            let stateLabel = 'Ready to query';
            let dotColor = '#94a3b8';
            let textColor = '#64748b';

            if (loadingRecs) {
              stateLabel = 'Loading';
              dotColor = '#3b82f6';
              textColor = '#2563eb';
            } else if (apiError) {
              stateLabel = 'Request failed';
              dotColor = '#ef4444';
              textColor = '#dc2626';
            } else if (locationWarning) {
              stateLabel = 'Check location';
              dotColor = '#f59e0b';
              textColor = '#b45309';
            } else if (rawRecommendations.length > 0) {
              stateLabel = 'Results received';
              dotColor = '#10b981';
              textColor = '#059669';
            }

            return (
              <div id="request-state-indicator" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    background: dotColor,
                  }}
                />
                <span style={{ fontSize: 12, color: textColor, fontWeight: 600 }}>
                  {stateLabel}
                </span>
              </div>
            );
          })()}
        </div>
      </header>

      {/* ── Main Planner Container ── */}
      <div style={styles.recsMainContainer}>
        {/* Compact Page Introduction */}
        <div style={{ marginBottom: 20 }}>
          <h1 style={styles.recsTitle}>Events & Travel Planner</h1>
          <p style={styles.recsSubtitle}>
            Explore Sri Lankan destinations, compare recommendations, and plan your trip with updated weather advisories.
          </p>
        </div>

        {/* ── Primary Form Controls Card ── */}
        <div style={styles.topControlCard}>
          <div className="trip-form-grid">
            {/* Preference Input */}
            <div>
              <label style={styles.controlLabel}>Travel preferences (optional)</label>
              <div style={styles.inputIconWrapper}>
                <span style={{ fontSize: 16, color: '#2563eb' }}>🪄</span>
                <input
                  id="user-preference-input"
                  value={userPrefText}
                  onChange={(e) => setUserPrefText(e.target.value)}
                  onKeyDown={(e) =>
                    e.key === 'Enter' &&
                    fetchRecommendationsData(userPrefText, plannedDate, origin, days, transportMode)
                  }
                  placeholder="e.g. cool weather, nature and hiking"
                  style={styles.prefInputWithIcon}
                  aria-label="Preference text"
                />
              </div>
            </div>

            {/* Duration (Days) */}
            <div>
              <label style={styles.controlLabel}>📅 Duration</label>
              <select
                id="days-select"
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                style={styles.selectControl}
                aria-label="Trip duration in days"
              >
                <option value={1}>1 Day</option>
                <option value={2}>2 Days</option>
                <option value={3}>3 Days</option>
                <option value={4}>4 Days</option>
                <option value={5}>5 Days</option>
              </select>
            </div>

            {/* Transport Mode */}
            <div>
              <label style={styles.controlLabel}>🚗 Transport</label>
              <select
                id="transport-select"
                value={transportMode}
                onChange={(e) => setTransportMode(e.target.value)}
                style={styles.selectControl}
                aria-label="Transportation Mode"
              >
                <option value="car">Car (🚗)</option>
                <option value="bus">Bus (🚌)</option>
                <option value="train">Train (🚆)</option>
              </select>
            </div>

            {/* Visit Date */}
            <div>
              <label style={styles.controlLabel}>🗓️ Visit Date</label>
              <input
                id="visit-date-input"
                type="date"
                min={tomorrowStr}
                max={maxDateStr}
                value={plannedDate}
                onChange={(e) => {
                  const val = e.target.value;
                  if (!val || val < tomorrowStr) {
                    setPlannedDate(tomorrowStr);
                  } else if (val > maxDateStr) {
                    setPlannedDate(maxDateStr);
                  } else {
                    setPlannedDate(val);
                  }
                }}
                style={styles.dateInputControl}
                aria-label="Planned trip date"
              />
            </div>

            {/* Main Submit Action Button */}
            <div>
              <button
                id="get-recommendations-btn"
                onClick={() => fetchRecommendationsData(userPrefText, plannedDate, origin, days, transportMode)}
                disabled={loadingRecs}
                style={styles.mainActionBtn}
              >
                <span style={{ fontSize: 16 }}>✨</span>
                <span>{loadingRecs ? 'Fetching...' : 'Get Recommendations'}</span>
              </button>
            </div>
          </div>

          {/* Quick Preset Queries */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: '#64748b' }}>Quick prompts:</span>
            <button
              onClick={() => {
                const text = 'I want to go to a quiet cold place';
                setUserPrefText(text);
                fetchRecommendationsData(text, plannedDate, origin, days, transportMode);
              }}
              style={styles.controlChipBtn}
            >
              <span>❄️</span> Cold & Quiet Place
            </button>

            <button
              onClick={() => {
                const text = 'beach and coastal nature adventure';
                setUserPrefText(text);
                fetchRecommendationsData(text, plannedDate, origin, days, transportMode);
              }}
              style={styles.controlChipBtn}
            >
              <span>🏖️</span> Beach & Coastal Nature
            </button>

            <button
              onClick={() => {
                const text = 'ancient cultural heritage and temples';
                setUserPrefText(text);
                fetchRecommendationsData(text, plannedDate, origin, days, transportMode);
              }}
              style={styles.controlChipBtn}
            >
              <span>🏛️</span> Heritage & Temples
            </button>

            {userPrefText && (
              <button
                onClick={() => setUserPrefText('')}
                style={{ ...styles.controlChipBtn, background: '#f1f5f9', color: '#64748b', borderColor: '#cbd5e1' }}
              >
                ✕ Clear Prompt
              </button>
            )}
          </div>
          {/* Weather forecast range notice for the selected trip dates */}
          {(() => {
            const limit = new Date();
            limit.setDate(limit.getDate() + WEATHER_FORECAST_DAYS_AHEAD);
            const limitStr = formatDateStr(limit);
            const [y, m, d] = plannedDate.split('-').map(Number);
            const tripEndStr = formatDateStr(new Date(y, m - 1, d + (Number(days) || 1) - 1));
            if (plannedDate > limitStr) {
              return (
                <div style={styles.forecastRangeHint}>
                  ⚠️ Weather forecasts are only available up to {WEATHER_FORECAST_DAYS_AHEAD} days ahead. Weather data may not be available for this date.
                </div>
              );
            }
            if (tripEndStr > limitStr) {
              return (
                <div style={styles.forecastRangeHint}>
                  ⚠️ Weather forecasts only cover {WEATHER_FORECAST_DAYS_AHEAD} days ahead. Later days of your trip may not have weather data.
                </div>
              );
            }
            return null;
          })()}
        </div>

        {/* ── Error Banner State ── */}
        {apiError && !loadingRecs && (
          <div id="api-error-banner" style={styles.errorBox} role="alert">
            <div style={{ fontSize: 24 }}>⚠️</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#991b1b' }}>Backend Service Notice</div>
              <div style={{ fontSize: 13, color: '#b91c1c', marginTop: 2 }}>{apiError}</div>
              <div style={{ fontSize: 12, color: '#7f1d1d', marginTop: 4 }}>
                The application preserves actual server responses and does not synthesize mock results.
              </div>
            </div>
            <button
              id="retry-request-btn"
              onClick={() => fetchRecommendationsData(userPrefText, plannedDate, origin, days, transportMode)}
              style={styles.retryBtn}
            >
              ↻ Retry Request
            </button>
          </div>
        )}

        {/* ── Location Warning (place outside Sri Lanka / misspelled) ── */}
        {locationWarning && !loadingRecs && (
          <div
            id="location-warning-banner"
            role="alert"
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 12,
              padding: '14px 16px',
              marginBottom: 16,
              borderRadius: 12,
              background: '#fffbeb',
              border: '1px solid #fcd34d',
            }}
          >
            <div style={{ fontSize: 24 }}>📍</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#92400e' }}>Location not found in Sri Lanka</div>
              <div style={{ fontSize: 13, color: '#b45309', marginTop: 2 }}>{locationWarning}</div>
            </div>
          </div>
        )}

        {/* ── Loading Indicator State ── */}
        {loadingRecs && (
          <div id="loading-indicator-box" style={styles.loadingBox}>
            <div style={{ fontSize: 28, marginBottom: 10 }}>🧭</div>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>
              Planning your trip...
            </div>
            <div style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>
              Finding the best destinations and route for your dates.
            </div>
          </div>
        )}

        {/* ── Initial Empty State ── */}
        {!loadingRecs && !hasSearched && rawRecommendations.length === 0 && !apiError && (
          <div style={styles.emptyInitialCard}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>🗺️</div>
            <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
              Ready to Plan Your Trip?
            </h3>
            <p style={{ fontSize: 13.5, color: '#64748b', margin: 0, maxWidth: '520px', lineHeight: '1.5' }}>
              Click <strong>Get Recommendations</strong> above to query the backend and generate a
              multi-day itinerary alongside detailed destination analytics.
            </p>
          </div>
        )}

        {/* ═══════════════════════════════════════════════════════════════════════════ */}
        {/* BACKEND ROUTE RECOMMENDATION (HERO CARD - Visually Separate & Unaltered)    */}
        {/* ═══════════════════════════════════════════════════════════════════════════ */}
        {!loadingRecs && hasSearched && recommendedRoute && (
          <div id="recommended-route-hero-card" style={styles.routeHeroCard}>
            {/* Header Disclaimer & Badges */}
            <div style={styles.routeHeroHeader}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <span style={styles.trophyBadge}>RECOMMENDED MULTI-DAY ROUTE</span>
                <span style={styles.rankDecisionBadge}>
                  #{recommendedRoute.rank || 1} {recommendedRoute.decision || 'Recommended'}
                </span>
              </div>
              <div style={styles.routeScoreBox}>
                <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600 }}>Route Score</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 2 }}>
                  {recommendedRoute.overall_route_score != null ? (
                    <>
                      <span style={styles.routeScoreNum}>{recommendedRoute.overall_route_score}</span>
                      <span style={styles.routeScoreMax}>/ 100</span>
                    </>
                  ) : (
                    <span style={{ fontSize: 14, color: '#64748b' }}>Not available</span>
                  )}
                </div>
              </div>
            </div>

            {/* Route Sequence Title */}
            <h2 style={styles.routeSequenceTitle}>
              {recommendedRoute.route_display || (recommendedRoute.route ? recommendedRoute.route.join(' → ') : '')}
            </h2>

            <div style={styles.routeDisclaimerNotice}>
              ℹ️ Note: These filters change the destination list, not your itinerary. The multi-day route sequence and travel scores are pre-computed by the backend route engine.
            </div>

            {/* Stop Weather Advisory Notice (when selected destination is part of route) */}
            {routeStops.length > 0 && (
              <div id="route-stop-weather-summary" style={styles.routeWeatherSummaryBox}>
                {routeStopForecasts.map((f) => (
                  <span key={f.stop} style={styles.routeStopWeatherChip}>
                    <strong>{f.stop}</strong>
                    <span style={{ color: '#64748b', fontSize: 11.5 }}>Day {f.day} · {f.visitDate}</span>
                    {f.status === 'loading' && <span style={{ color: '#64748b' }}>…</span>}
                    {f.status === 'error' && <span style={{ color: '#64748b' }}>N/A</span>}
                    {f.status === 'out_of_range' && (
                      <span style={{ color: '#92400e' }}>📅 Forecast not available yet</span>
                    )}
                    {f.status === 'ok' && (
                      <span>
                        {f.icon} {f.description}
                        {f.maxTemp != null && ` · ${Math.round(f.maxTemp)}°C`}
                      </span>
                    )}
                  </span>
                ))}
              </div>
            )}
            {routeStopForecasts.some((f) => f.status === 'out_of_range') && (
              <div style={{ fontSize: 11.5, color: '#64748b', marginTop: 6 }}>
                Weather forecasts only cover the next 15 days. Check again closer to your trip.
              </div>
            )}

            {/* Stat Pills Row */}
            <div style={styles.statPillsRow}>
              <span style={styles.statPill}>
                🚗 <strong>{recommendedRoute.total_distance_km} km</strong> total
              </span>
              <span style={styles.statPill}>
                ⏱ <strong>{recommendedRoute.total_travel_time}</strong> travel time
              </span>
              <span style={styles.statPill}>
                📅 <strong>{recommendedRoute.days} Days</strong>
              </span>
              <span
                style={{
                  ...styles.statPill,
                  background: recommendedRoute.feasible ? '#ecfdf5' : '#fef2f2',
                  color: recommendedRoute.feasible ? '#047857' : '#b91c1c',
                  borderColor: recommendedRoute.feasible ? '#a7f3d0' : '#fecaca',
                }}
              >
                {recommendedRoute.feasible ? '✓ Feasible Schedule' : '⚠ High Travel Time'}
              </span>
            </div>

            {/* Route Timeline */}
            <div style={styles.sectionDivider}>
              <h3 style={styles.subSectionTitle}>📍 Route Sequence</h3>
              <div style={styles.timelineContainer}>
                {(recommendedRoute.route || []).map((stop, idx) => {
                  const segment = (recommendedRoute.segments || [])[idx];
                  const isStopWeatherSelected = stop === selectedWeatherDestination;
                  return (
                    <React.Fragment key={idx}>
                      <div style={styles.timelineNode}>
                        <div style={styles.timelineDot} />
                        <span style={styles.timelineNodeName}>{stop}</span>
                        {isStopWeatherSelected && isMatchingDestData && activeWeatherData && (
                          <span
                            id={`route-stop-weather-pill-${stop.toLowerCase().replace(/\s+/g, '-')}`}
                            style={{
                              marginLeft: 8,
                              padding: '2px 8px',
                              borderRadius: '8px',
                              fontSize: '11px',
                              fontWeight: 700,
                              background:
                                activeAdvisory.level === 'Caution'
                                  ? '#fee2e2'
                                  : activeAdvisory.level === 'Notice'
                                  ? '#fef3c7'
                                  : '#ecfdf5',
                              color:
                                activeAdvisory.level === 'Caution'
                                  ? '#991b1b'
                                  : activeAdvisory.level === 'Notice'
                                  ? '#92400e'
                                  : '#065f46',
                              border: `1px solid ${
                                activeAdvisory.level === 'Caution'
                                  ? '#fca5a5'
                                  : activeAdvisory.level === 'Notice'
                                  ? '#fcd34d'
                                  : '#a7f3d0'
                              }`,
                            }}
                          >
                            {activeWeatherData.current?.weatherInfo?.icon} {activeWeatherData.current?.weatherInfo?.description} • {activeAdvisory.outdoorDisruption} (Model Timestep: {activeWeatherData.validTime})
                          </span>
                        )}
                      </div>
                      {segment && (
                        <div style={styles.timelineArrowRow}>
                          <div style={styles.timelineLine} />
                          <span style={styles.segmentTimeBadge}>
                            ↓ {segment.estimated_travel_time} ({segment.distance_km} km)
                          </span>
                        </div>
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
            </div>

            {/* Route Segments */}
            {recommendedRoute.segments && recommendedRoute.segments.length > 0 && (
              <div style={styles.sectionDivider}>
                <h3 style={styles.subSectionTitle}>🚗 Transfer Segments</h3>
                <div style={styles.segmentsGrid}>
                  {recommendedRoute.segments.map((seg, sIdx) => (
                    <div key={sIdx} style={styles.segmentCard}>
                      <div style={styles.segmentHeader}>
                        <span>{seg.from} → {seg.to}</span>
                        {seg.is_estimated_distance && (
                          <span style={styles.estimatedDistBadge}>Estimated</span>
                        )}
                      </div>
                      <div style={styles.segmentMetricsRow}>
                        <span>📏 <strong>{seg.distance_km} km</strong></span>
                        <span>⏱ <strong>{seg.estimated_travel_time}</strong></span>
                      </div>
                      {seg.warnings && seg.warnings.length > 0 && (
                        <div style={styles.segmentWarningsBox}>
                          {seg.warnings.map((w, wIdx) => (
                            <div key={wIdx} style={{ fontSize: 11.5, color: '#b45309' }}>⚠ {w}</div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 5b. PLACES TO SEE ALONG THE ROUTE */}
            {recommendedRoute.places_to_visit && recommendedRoute.places_to_visit.length > 0 && (
              <div style={styles.sectionDivider}>
                <h3 style={styles.subSectionTitle}>📸 Places to See Along the Route</h3>
                <div style={styles.segmentsGrid}>
                  {recommendedRoute.places_to_visit.map((stopInfo, pIdx) => (
                    <div key={pIdx} style={styles.segmentCard}>
                      <div style={styles.segmentHeader}>
                        <span>📍 {stopInfo.stop}</span>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                        {(stopInfo.places || []).map((place, plIdx) => (
                          <div key={plIdx} style={styles.placeItem}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                              <span style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>{place.name}</span>
                              {place.category && <span style={styles.placeCategoryBadge}>{place.category}</span>}
                            </div>
                            {place.description && (
                              <div style={{ fontSize: 12, color: '#475569', marginTop: 3 }}>{place.description}</div>
                            )}
                            {place.visit_duration && (
                              <div style={{ fontSize: 11.5, color: '#059669', fontWeight: 600, marginTop: 3 }}>⏱ {place.visit_duration}</div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            
            {/* Daily Itinerary */}
            {recommendedRoute.daily_plan && recommendedRoute.daily_plan.length > 0 && (
              <div style={styles.sectionDivider}>
                <h3 style={styles.subSectionTitle}>🗓️ Daily Schedule Plan</h3>
                <div style={styles.dailyPlanGrid}>
                  {recommendedRoute.daily_plan.map((dp, dIdx) => (
                    <div key={dIdx} style={styles.dailyPlanCard}>
                      <div style={styles.dayBadge}>DAY {dp.day}</div>
                      <div style={styles.dayRouteHeader}>{dp.route}</div>
                      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 10 }}>⏱ Travel: {dp.travel_time}</div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: '#334155', marginBottom: 6 }}>Scheduled Activities:</div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {(dp.activities || []).map((act, aIdx) => (
                          <div key={aIdx} style={styles.activityItem}>
                            <span>• {act.name}</span>
                            <span style={{ fontSize: 11.5, color: '#059669', fontWeight: 600 }}>{act.time}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Why Recommended & Trade-offs */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginTop: 24 }}>
              <div style={styles.reasonsCard}>
                <h4 style={{ ...styles.cardSubHeader, color: '#047857' }}>Why AI Recommends This Route</h4>
                <ul style={styles.bulletList}>
                  {(recommendedRoute.why_recommended || []).map((reason, rIdx) => (
                    <li key={rIdx} style={styles.whyListItem}>
                      <span style={{ color: '#10b981', fontWeight: 800 }}>✓</span> {reason}
                    </li>
                  ))}
                </ul>
              </div>

              {recommendedRoute.tradeoffs && recommendedRoute.tradeoffs.length > 0 && (
                <div style={styles.tradeoffsCard}>
                  <h4 style={{ ...styles.cardSubHeader, color: '#b45309' }}>Things to Consider</h4>
                  <ul style={styles.bulletList}>
                    {recommendedRoute.tradeoffs.map((to, tIdx) => (
                      <li key={tIdx} style={styles.tradeoffListItem}>
                        <span style={{ color: '#f59e0b', fontWeight: 800 }}>⚠</span> {to}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ═══════════════════════════════════════════════════════════════════════════ */}
        {/* LIVE OPEN-METEO WEATHER ADVISORY & FORECAST PANEL                           */}
        {/* ═══════════════════════════════════════════════════════════════════════════ */}
        {!loadingRecs && hasSearched && selectedWeatherDestination && (
          <div id="weather-advisory-panel" style={styles.weatherPanelCard}>
            {/* Panel Header */}
            <div style={styles.weatherPanelHeader}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 24 }}>🌤️</span>
                <div>
                  <h3 style={styles.weatherPanelTitle}>
                    Weather Advisory & Forecast: {selectedWeatherDestination}
                  </h3>
                  <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>
                    {relevantHourly?.covered && !relevantHourly?.isToday
                      ? `🗓️ Forecast for Visit Date: ${relevantHourly.targetDate || plannedDate}`
                      : '🕒 Current weather estimate & upcoming hours'}{' '}
                    • Applicable Timestep: <strong>{activeWeatherData?.validTime || 'Current'}</strong> (Asia/Colombo)
                  </div>
                </div>
              </div>

              {/* Destination Selector & Controls */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>

                {/* Manual Refresh Button (bypasses cache, subject to 5s rate-limit cooldown) */}
                <button
                  id="manual-weather-refresh-btn"
                  onClick={handleManualRefresh}
                  disabled={weatherLoading || manualRefreshCooldown > 0}
                  style={{
                    ...styles.weatherRefreshBtn,
                    opacity: weatherLoading || manualRefreshCooldown > 0 ? 0.7 : 1,
                    cursor: weatherLoading || manualRefreshCooldown > 0 ? 'not-allowed' : 'pointer',
                  }}
                  title="Bypass cache and fetch latest Open-Meteo numerical forecast"
                  aria-label="Refresh weather data"
                >
                  {weatherLoading
                    ? '↻ Refreshing...'
                    : manualRefreshCooldown > 0
                    ? `↻ Cooldown (${manualRefreshCooldown}s)`
                    : '↻ Refresh Weather'}
                </button>
              </div>
            </div>

            {/* Stale Data Warning Banner (Visible on Stale State) */}
            {weatherIsStale && (
              <div id="weather-stale-banner" style={styles.weatherStaleBanner}>
                ⚠️ <strong>Retained data is stale.</strong> Open-Meteo refresh attempt failed ({weatherError || 'Network timeout'}).
                Displaying last retrieved forecast from {weatherLastSuccessTime || 'earlier session'}.
              </div>
            )}

            {/* Error Banner when no data available (Visible on Failure) */}
            {weatherError && !isMatchingDestData && !weatherLoading && (
              <div id="weather-error-box" style={styles.weatherErrorBanner}>
                <span>⚠️ {weatherError}</span>
                <button
                  onClick={() => loadWeather(selectedWeatherDestination, true)}
                  style={styles.retryWeatherBtn}
                >
                  Retry
                </button>
              </div>
            )}

            {/* Destination Switch Loading Placeholder */}
            {(!isMatchingDestData || (weatherLoading && !weatherData)) && (
              <div id="weather-loading-box" style={styles.weatherDestSwitchLoading}>
                <span style={{ fontSize: 22 }}>⏳</span>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#1e293b' }}>
                    Retrieving Open-Meteo numerical forecast for {selectedWeatherDestination}...
                  </div>
                  <div style={{ fontSize: 11.5, color: '#64748b' }}>
                    Loading dedicated destination coordinates and separate model telemetry.
                  </div>
                </div>
              </div>
            )}

            {/* Active Weather Content */}
            {isMatchingDestData && activeWeatherData && (
              <div style={{ marginTop: 14 }}>
                {/* Relevant Hourly Forecast (Always Visible for Selected Date) */}
                <div style={{ marginTop: 16 }}>
                  <div style={styles.subCardHeader}>
                    <span>
                      📅 Hourly Forecast: {relevantHourly?.targetDate || plannedDate}{' '}
                      {relevantHourly?.isToday ? '(Today — Upcoming Hours)' : '(Selected Visit Date)'}
                    </span>
                  </div>

                  {relevantHourly && !relevantHourly.covered ? (
                    <div id="forecast-unavailable-box" style={styles.forecastUnavailableNotice}>
                      <span style={{ fontSize: 18 }}>⚠️</span>
                      <div>
                        <strong>Forecast unavailable for this date</strong>
                        <div style={{ fontSize: 12, marginTop: 2 }}>
                          {relevantHourly.message || `The selected visit date (${plannedDate}) is outside this application's configured 15-day forecast window. Current model conditions remain displayed separately above.`}
                        </div>
                      </div>
                    </div>
                  ) : relevantHourly && relevantHourly.items && relevantHourly.items.length > 0 ? (
                    <div id="weather-hourly-strip" style={styles.hourlyScrollStrip}>
                      {relevantHourly.items.map((item, hIdx) => (
                        <div key={hIdx} style={styles.hourlyPillCard}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: '#475569' }}>
                            {item.hourStr}
                          </div>
                          <div style={{ fontSize: 20, margin: '4px 0' }}>
                            {item.weatherInfo?.icon || '🌤️'}
                          </div>
                          <div style={{ fontSize: 13, fontWeight: 800, color: '#0f172a' }}>
                            {item.temperature}°C
                          </div>
                          <div style={{ fontSize: 10.5, color: '#2563eb', marginTop: 2 }}>
                            🌧️ {item.precipitationProbability != null ? `${item.precipitationProbability}%` : '--'}
                          </div>
                          <div style={{ fontSize: 10, color: '#64748b' }}>
                            {item.precipitation ? `${item.precipitation}mm` : '0mm'}
                          </div>
                          <div style={{ fontSize: 9.5, color: '#64748b' }}>
                            💨 {item.windSpeed} km/h
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, color: '#64748b', padding: '10px 0' }}>
                      No hourly forecast points available for this selection.
                    </div>
                  )}
                </div>

              </div>
            )}
          </div>
        )}

        {/* ═══════════════════════════════════════════════════════════════════════════ */}
        {/* SUPPORTING DESTINATIONS SECTION WITH ACTIVE DERIVED FILTERS                 */}
        {/* ═══════════════════════════════════════════════════════════════════════════ */}
        {!loadingRecs && hasSearched && rawRecommendations.length > 0 && (
          <div style={{ marginTop: 36 }}>
            {/* Section Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 12 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 20, color: '#2563eb' }}>🗺️</span>
                  <h2 style={{ fontSize: 20, fontWeight: 800, color: '#0f172a', margin: 0 }}>
                    Recommended Destinations to Visit
                  </h2>
                  <span id="destinations-count-badge" style={styles.countBadge}>
                    Showing {displayedRecommendations.length} of {rawRecommendations.length}
                  </span>
                </div>
                <div style={{ fontSize: 12.5, color: '#64748b', marginTop: 4 }}>
                  These filters change the destination list, not your itinerary.
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {/* Secondary Filters Expand/Collapse Toggle */}
                <button
                  id="toggle-filter-panel-btn"
                  onClick={() => setIsFilterPanelOpen((prev) => !prev)}
                  style={{
                    ...styles.filterToggleBtn,
                    background: isFilterPanelOpen ? '#eff6ff' : '#ffffff',
                    borderColor: isFilterPanelOpen ? '#3b82f6' : '#cbd5e1',
                    color: isFilterPanelOpen ? '#1d4ed8' : '#334155',
                  }}
                  aria-expanded={isFilterPanelOpen}
                >
                  ⚙️ Filter Options {activeFilterCount > 0 ? `(${activeFilterCount})` : ''} {isFilterPanelOpen ? '▲ Hide' : '▼ Expand'}
                </button>

                {hasActiveFilters && (
                  <button id="clear-all-filters-btn" onClick={handleClearFilters} style={styles.clearFiltersBtn}>
                    ✕ Clear Filters
                  </button>
                )}
              </div>
            </div>

            {/* Compact Active Filter Summary Bar (Always Visible when filters active) */}
            {hasActiveFilters && (
              <div id="active-filters-summary-bar" style={styles.activeFiltersBar}>
                <span style={{ fontSize: 12, fontWeight: 700, color: '#475569' }}>Active filters:</span>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                  {selectedInterests.map((interestId) => {
                    const opt = VERIFIED_INTEREST_OPTIONS.find((o) => o.id === interestId);
                    return (
                      <span key={interestId} style={styles.activeFilterPill}>
                        {opt?.icon} {opt?.label}
                        <button
                          onClick={() => setSelectedInterests((prev) => prev.filter((i) => i !== interestId))}
                          style={styles.removeActiveFilterBtn}
                          title={`Remove ${opt?.label}`}
                          aria-label={`Remove ${opt?.label} filter`}
                        >
                          ✕
                        </button>
                      </span>
                    );
                  })}
                  {preferLowerCrowds && (
                    <span style={styles.activeFilterPill}>
                      👥 Lower crowds first
                      <button
                        onClick={() => setPreferLowerCrowds(false)}
                        style={styles.removeActiveFilterBtn}
                        title="Turn off lower crowd sorting"
                        aria-label="Remove lower crowd preference"
                      >
                        ✕
                      </button>
                    </span>
                  )}
                  {filterLowCrowdOnly && (
                    <span style={styles.activeFilterPill}>
                      👥 Low crowd only (&lt;110)
                      <button
                        onClick={() => setFilterLowCrowdOnly(false)}
                        style={styles.removeActiveFilterBtn}
                        title="Turn off strict low crowd filter"
                        aria-label="Remove low crowd only filter"
                      >
                        ✕
                      </button>
                    </span>
                  )}
                  {weatherFilter !== 'all' && (
                    <span style={styles.activeFilterPill}>
                      🌤️ {weatherFilter === 'excellent' ? 'Excellent weather' : 'Good & Excellent weather'}
                      <button
                        onClick={() => setWeatherFilter('all')}
                        style={styles.removeActiveFilterBtn}
                        title="Reset weather filter"
                        aria-label="Remove weather conditions filter"
                      >
                        ✕
                      </button>
                    </span>
                  )}
                  {showShortlistOnly && (
                    <span style={styles.activeFilterPill}>
                      ★ Shortlisted only
                      <button
                        onClick={() => setShowShortlistOnly(false)}
                        style={styles.removeActiveFilterBtn}
                        title="Show all destinations"
                        aria-label="Remove shortlist only filter"
                      >
                        ✕
                      </button>
                    </span>
                  )}
                  {excludedPlaces.map((p) => (
                    <span key={p} style={{ ...styles.activeFilterPill, background: '#fee2e2', color: '#991b1b', borderColor: '#fca5a5' }}>
                      🚫 Excluded: {p}
                      <button
                        onClick={() => handleRestorePlace(p)}
                        style={{ ...styles.removeActiveFilterBtn, color: '#991b1b' }}
                        title={`Restore ${p}`}
                        aria-label={`Restore ${p}`}
                      >
                        ✕
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Expandable Secondary Filter Panel */}
            {isFilterPanelOpen && (
              <div id="secondary-filter-panel" style={styles.filterControlsPanel}>
                {/* Row 1: Activity-Interest Multi-Select Chips */}
                <div>
                  <div style={styles.filterSectionTitle}>
                    <span>🎯 Activity & Interest Filter:</span>
                    <span style={styles.filterHelpText}>
                      (Matches verified destination activities & benchmark categories)
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 6 }}>
                    {VERIFIED_INTEREST_OPTIONS.map((item) => {
                      const isSelected = selectedInterests.includes(item.id);
                      return (
                        <button
                          key={item.id}
                          id={`interest-chip-${item.id}`}
                          onClick={() => {
                            setSelectedInterests((prev) =>
                              isSelected ? prev.filter((i) => i !== item.id) : [...prev, item.id]
                            );
                          }}
                          style={{
                            ...styles.categoryChip,
                            background: isSelected ? '#dbeafe' : '#ffffff',
                            color: isSelected ? '#1d4ed8' : '#334155',
                            borderColor: isSelected ? '#3b82f6' : '#cbd5e1',
                            fontWeight: isSelected ? 700 : 500,
                          }}
                        >
                          <span>{item.icon}</span> {item.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Row 2: Crowd, Weather, and Display Options */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14, marginTop: 14 }}>
                  {/* Prefer Lower Crowds (Stable Sort) */}
                  <div style={styles.filterToggleCard}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', margin: 0 }}>
                      <input
                        id="prefer-lower-crowds-toggle"
                        type="checkbox"
                        checked={preferLowerCrowds}
                        onChange={(e) => setPreferLowerCrowds(e.target.checked)}
                        style={{ width: 17, height: 17, accentColor: '#059669', cursor: 'pointer' }}
                      />
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>
                          Prefer lower crowds
                        </div>
                        <div style={{ fontSize: 11, color: '#64748b' }}>
                          Prioritizes lower crowd first without hiding results
                        </div>
                      </div>
                    </label>
                  </div>

                  {/* Strict Filter "Low Crowd Only" */}
                  <div style={styles.filterToggleCard}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', margin: 0 }}>
                      <input
                        id="strict-low-crowd-toggle"
                        type="checkbox"
                        checked={filterLowCrowdOnly}
                        onChange={(e) => setFilterLowCrowdOnly(e.target.checked)}
                        style={{ width: 17, height: 17, accentColor: '#059669', cursor: 'pointer' }}
                      />
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>
                          Low crowd only
                        </div>
                        <div style={{ fontSize: 11, color: '#64748b' }}>
                          Hides destinations with crowd &ge; 110 or Moderate/High
                        </div>
                      </div>
                    </label>
                  </div>

                  {/* Weather Conditions Filter */}
                  <div style={styles.filterToggleCard}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a', marginBottom: 4 }}>
                      🌤️ Weather conditions filter
                    </div>
                    <select
                      id="weather-conditions-select"
                      value={weatherFilter}
                      onChange={(e) => setWeatherFilter(e.target.value)}
                      style={styles.filterSelect}
                      aria-label="Filter by weather conditions"
                    >
                      <option value="all">All Weather conditions</option>
                      <option value="good_excellent">Good & Excellent Only</option>
                      <option value="excellent">Excellent Only</option>
                    </select>
                    <div style={{ fontSize: 10.5, color: '#64748b', marginTop: 3 }}>
                      Weather conditions (API supplied)
                    </div>
                  </div>

                  {/* Shortlist Filter Option */}
                  <div style={styles.filterToggleCard}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', margin: 0 }}>
                      <input
                        id="show-shortlist-only-toggle"
                        type="checkbox"
                        checked={showShortlistOnly}
                        onChange={(e) => setShowShortlistOnly(e.target.checked)}
                        disabled={shortlist.length === 0}
                        style={{ width: 17, height: 17, accentColor: '#d97706', cursor: 'pointer' }}
                      />
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: shortlist.length === 0 ? '#94a3b8' : '#0f172a' }}>
                          ★ Show Shortlisted ({shortlist.length})
                        </div>
                        <div style={{ fontSize: 11, color: '#64748b' }}>
                          View only bookmarked destinations
                        </div>
                      </div>
                    </label>
                  </div>
                </div>

                {/* Excluded Places in Filter Panel */}
                {excludedPlaces.length > 0 && (
                  <div id="excluded-destinations-bar" style={styles.excludedSection}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: '#991b1b' }}>
                      Excluded destinations ({excludedPlaces.length}):
                    </span>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                      {excludedPlaces.map((p) => (
                        <span key={p} style={styles.excludedChip}>
                          {p}
                          <button
                            onClick={() => handleRestorePlace(p)}
                            style={styles.unexcludeBtn}
                            title={`Restore ${p}`}
                            aria-label={`Restore ${p}`}
                          >
                            ✕
                          </button>
                        </span>
                      ))}
                      <button
                        id="restore-all-excluded-btn"
                        onClick={() => setExcludedPlaces([])}
                        style={styles.restoreAllBtn}
                      >
                        Restore All
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ── No Matching Results State ── */}
            {displayedRecommendations.length === 0 && (
              <div id="no-matching-results-card" style={styles.emptyFilteredBox}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>🔍</div>
                <h4 style={{ fontSize: 16, fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                  No destinations match your active filters
                </h4>
                <p style={{ fontSize: 13, color: '#64748b', margin: '0 0 16px 0' }}>
                  Try removing interest tags or resetting weather and crowd filters to see original recommendations.
                </p>
                <button onClick={handleClearFilters} style={styles.mainActionBtn}>
                  Reset All Filters ({rawRecommendations.length} Destinations)
                </button>
              </div>
            )}

            {/* ── Destination Cards Grid ── */}
            <div id="destinations-cards-list" style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 14 }}>
              {displayedRecommendations.map((rec, index) => {
                const rank = rec.ai_recommendation?.rank || index + 1;
                const rankBg =
                  rank === 1
                    ? '#16a34a'
                    : rank === 2
                    ? '#eab308'
                    : rank === 3
                    ? '#f97316'
                    : rank === 4
                    ? '#3b82f6'
                    : '#64748b';

                const overallScore =
                  rec.ai_recommendation?.overall_score != null
                    ? rec.ai_recommendation.overall_score
                    : rec.score != null
                    ? rec.score
                    : 'Not available';

                const crowdText =
                  rec.crowd_label ||
                  rec.crowd_safety?.crowd_level ||
                  (rec.crowd != null ? (rec.crowd < 110 ? 'Low' : rec.crowd < 200 ? 'Moderate' : 'High') : 'Not available');

                const crowdColor =
                  crowdText === 'Low'
                    ? '#166534'
                    : crowdText === 'Moderate'
                    ? '#d97706'
                    : crowdText === 'High' || crowdText === 'Very High'
                    ? '#dc2626'
                    : '#64748b';

                const distanceStr =
                  rec.travel_transport?.distance_km != null
                    ? `${rec.travel_transport.distance_km} km`
                    : 'Not available';

                const travelTimeStr =
                  rec.travel_transport?.estimated_travel_time || 'Not available';

                const topActName =
                  rec.activity_recommendations?.top_activity?.name || 'Local Sightseeing';

                const topActDuration =
                  rec.activity_recommendations?.top_activity?.duration_hours != null
                    ? `${rec.activity_recommendations.top_activity.duration_hours}h`
                    : '';

                const topActCategory =
                  rec.activity_recommendations?.top_activity?.category || '';

                const timingStr =
                  rec.event_timing?.best_activity_time || '';

                const decisionBadgeStr = (
                  rec.ai_recommendation?.decision ||
                  (overallScore >= 90
                    ? 'Highly Recommended'
                    : overallScore >= 80
                    ? 'Recommended'
                    : overallScore >= 70
                    ? 'Suitable'
                    : 'Consider')
                ).toUpperCase();

                const decisionBg = decisionBadgeStr.includes('HIGHLY')
                  ? '#dcfce7'
                  : decisionBadgeStr.includes('RECOMMENDED')
                  ? '#dcfce7'
                  : decisionBadgeStr.includes('SUITABLE')
                  ? '#fef9c3'
                  : '#ffedd5';

                const decisionColor = decisionBadgeStr.includes('HIGHLY')
                  ? '#15803d'
                  : decisionBadgeStr.includes('RECOMMENDED')
                  ? '#166534'
                  : decisionBadgeStr.includes('SUITABLE')
                  ? '#a16207'
                  : '#c2410c';

                const isShortlisted = shortlist.includes(rec.place);
                const isCompared = comparisonPlaces.includes(rec.place);
                const activitiesList = rec.activity_recommendations?.activities || [];

                return (
                  <div key={rec.place} className="destination-card" data-place={rec.place} style={styles.recItemCard}>
                    {/* Destination Image Thumbnail & Rank Badge */}
                    <div style={styles.recImageContainer}>
                      <img
                        src={getPlaceImage(rec.place, rec.image)}
                        alt={rec.place}
                        style={styles.recImage}
                      />
                      <div style={{ ...styles.rankBadge, background: rankBg }}>#{rank}</div>
                    </div>

                    {/* Destination Primary Information & Controls */}
                    <div style={styles.recInfoCol}>
                      {/* Top Header: Name, Score, Decision & Consistent Action Buttons */}
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 8, flexWrap: 'wrap' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                          <h3 style={styles.recPlaceTitle}>{rec.place}</h3>
                          <span
                            style={{
                              padding: '2px 8px',
                              borderRadius: '8px',
                              fontSize: '11px',
                              fontWeight: '800',
                              background: decisionBg,
                              color: decisionColor,
                            }}
                          >
                            {decisionBadgeStr}
                          </span>
                          <span style={styles.cardScorePill}>
                            Score:{' '}
                            {overallScore != null && overallScore !== 'Not available' ? (
                              <>
                                <strong>{overallScore}</strong> / 100
                              </>
                            ) : (
                              <strong>Not available</strong>
                            )}
                          </span>
                        </div>

                        {/* Consistent Unified Action Buttons */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          {/* Weather Button */}
                          <button
                            id={`weather-btn-${rec.place.toLowerCase().replace(/\s+/g, '-')}`}
                            onClick={() => {
                              setSelectedWeatherDestination(rec.place);
                              const el = document.getElementById('weather-advisory-panel');
                              if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                            }}
                            style={{
                              ...styles.iconActionBtn,
                              color: selectedWeatherDestination === rec.place ? '#0284c7' : '#475569',
                              background: selectedWeatherDestination === rec.place ? '#e0f2fe' : '#ffffff',
                              borderColor: selectedWeatherDestination === rec.place ? '#38bdf8' : '#cbd5e1',
                              fontWeight: selectedWeatherDestination === rec.place ? 700 : 500,
                            }}
                            title={`View live Open-Meteo weather advisory for ${rec.place}`}
                            aria-label={`View weather advisory for ${rec.place}`}
                          >
                            🌤️ {selectedWeatherDestination === rec.place ? 'Weather Active' : 'Weather'}
                          </button>

                          {/* Shortlist Button */}
                          <button
                            id={`shortlist-btn-${rec.place.toLowerCase().replace(/\s+/g, '-')}`}
                            onClick={() => toggleShortlist(rec.place)}
                            style={{
                              ...styles.iconActionBtn,
                              color: isShortlisted ? '#d97706' : '#475569',
                              background: isShortlisted ? '#fef3c7' : '#ffffff',
                              borderColor: isShortlisted ? '#f59e0b' : '#cbd5e1',
                            }}
                            title={isShortlisted ? 'Remove from Shortlist' : 'Add to Shortlist'}
                            aria-label={`Shortlist ${rec.place}`}
                          >
                            {isShortlisted ? '★ Saved' : '☆ Shortlist'}
                          </button>

                          {/* Compare Button */}
                          <button
                            id={`compare-btn-${rec.place.toLowerCase().replace(/\s+/g, '-')}`}
                            onClick={() => toggleComparison(rec.place)}
                            style={{
                              ...styles.iconActionBtn,
                              color: isCompared ? '#1d4ed8' : '#475569',
                              background: isCompared ? '#dbeafe' : '#ffffff',
                              borderColor: isCompared ? '#3b82f6' : '#cbd5e1',
                            }}
                            title="Compare up to 3 destinations"
                            aria-label={`Compare ${rec.place}`}
                          >
                            {isCompared ? '✓ Comparing' : '+ Compare'}
                          </button>

                          {/* Exclude Button */}
                          <button
                            id={`exclude-btn-${rec.place.toLowerCase().replace(/\s+/g, '-')}`}
                            onClick={() => handleExcludePlace(rec.place)}
                            style={styles.excludeIconBtn}
                            title={`Exclude ${rec.place} from view`}
                            aria-label={`Exclude ${rec.place}`}
                          >
                            ✕
                          </button>
                        </div>
                      </div>

                      {/* Concise Metrics Strip (Always Visible) */}
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginBottom: 8 }}>
                        <span style={styles.subPill}>
                          🚗 {distanceStr} ({travelTimeStr})
                        </span>
                        <span style={{ ...styles.subPill, color: crowdColor, fontWeight: 700 }}>
                          👥 Crowd: {crowdText} {rec.crowd != null ? `(${rec.crowd})` : ''}
                        </span>
                        <span style={styles.subPill}>
                          🎯 Main: {topActName} {topActDuration ? `(${topActDuration})` : ''}
                        </span>
                        {topActCategory && (
                          <span style={{ ...styles.subPill, background: '#f0fdf4', color: '#166534', fontWeight: 600 }}>
                            🏷️ {topActCategory}
                          </span>
                        )}
                      </div>

                      {/* Accessible Card Details Disclosure */}
                      <details className="dest-card-details" style={styles.cardDetailsDisclosure}>
                        <summary style={styles.cardDetailsSummary}>
                          View Details & Activities {activitiesList.length > 1 ? `(${activitiesList.length})` : ''} ▸
                        </summary>

                        <div style={styles.cardDetailsContent}>
                          <p style={styles.recPlaceDesc}>
                            {rec.desc || 'Top travel destination in Sri Lanka with optimal weather & crowd metrics.'}
                          </p>

                          {timingStr && (
                            <div style={{ fontSize: 12, color: '#334155', marginTop: 6, marginBottom: 8 }}>
                              ⏱ <strong>Optimal Activity Window:</strong> {timingStr} ({rec.event_timing?.best_time_period || 'standard'})
                            </div>
                          )}

                          {activitiesList.length > 0 && (
                            <div style={{ marginTop: 8 }}>
                              <div style={{ fontSize: 11.5, fontWeight: 700, color: '#1e293b', marginBottom: 6 }}>
                                Benchmark Activities ({activitiesList.length}):
                              </div>
                              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
                                {activitiesList.map((act, actIdx) => (
                                  <div key={actIdx} style={styles.miniActivityCard}>
                                    <div style={{ fontWeight: 700, color: '#1e293b' }}>{act.name}</div>
                                    <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
                                      ⏱ {act.duration_hours}h • Best: {act.best_time || 'anytime'}
                                    </div>
                                    <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
                                      {(act.categories || []).map((c, cIdx) => (
                                        <span key={cIdx} style={styles.miniCatTag}>
                                          {c}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {rec.ai_recommendation?.why_recommended && rec.ai_recommendation.why_recommended.length > 0 && (
                            <div style={{ marginTop: 8, padding: '8px 12px', background: '#f0fdf4', borderRadius: '8px', border: '1px solid #bbf7d0' }}>
                              <div style={{ fontSize: 11.5, fontWeight: 700, color: '#166534', marginBottom: 2 }}>Why Recommended:</div>
                              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 11.5, color: '#166534' }}>
                                {rec.ai_recommendation.why_recommended.map((w, wIdx) => <li key={wIdx}>{w}</li>)}
                              </ul>
                            </div>
                          )}

                          {rec.ai_recommendation?.tradeoffs && rec.ai_recommendation.tradeoffs.length > 0 && (
                            <div style={{ marginTop: 6, padding: '8px 12px', background: '#fffbeb', borderRadius: '8px', border: '1px solid #fef3c7' }}>
                              <div style={{ fontSize: 11.5, fontWeight: 700, color: '#92400e', marginBottom: 2 }}>Things to Consider:</div>
                              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 11.5, color: '#92400e' }}>
                                {rec.ai_recommendation.tradeoffs.map((t, tIdx) => <li key={tIdx}>{t}</li>)}
                              </ul>
                            </div>
                          )}
                        </div>
                      </details>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ═══════════════════════════════════════════════════════════════════════════ */}
        {/* DESTINATION COMPARISON DOCKED BAR & MODAL (Feature E - Up to 3 Destinations) */}
        {/* ═══════════════════════════════════════════════════════════════════════════ */}
        {comparisonPlaces.length > 0 && (
          <div id="comparison-dock-bar" style={styles.comparisonDockBar}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 13, fontWeight: 800, color: '#0f172a' }}>
                Comparing ({comparisonPlaces.length}/3):
              </span>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {comparisonPlaces.map((p) => (
                  <span key={p} style={styles.compareMiniChip}>
                    {p}
                    <button
                      onClick={() => toggleComparison(p)}
                      style={styles.removeCompareMiniBtn}
                      title={`Remove ${p}`}
                      aria-label={`Remove ${p} from comparison`}
                    >
                      ✕
                    </button>
                  </span>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <button
                id="open-side-by-side-comparison-btn"
                onClick={() => setIsComparisonOpen(true)}
                style={styles.openCompareBtn}
              >
                📊 Open Side-by-Side Comparison
              </button>
              <button
                id="clear-comparison-btn"
                onClick={clearComparison}
                style={styles.clearCompareBtn}
                title="Clear all comparison items"
              >
                Clear
              </button>
            </div>
          </div>
        )}

        {/* ── Comparison Full Modal ── */}
        {isComparisonOpen && comparedDestinationObjects.length > 0 && (
          <div id="comparison-modal-backdrop" style={styles.modalBackdrop}>
            <div style={styles.modalContainer}>
              {/* Modal Header */}
              <div style={styles.modalHeader}>
                <div>
                  <h3 style={{ fontSize: 20, fontWeight: 800, color: '#0f172a', margin: 0 }}>
                    Destination Comparison ({comparedDestinationObjects.length} Destinations)
                  </h3>
                  <div style={{ fontSize: 12.5, color: '#64748b', marginTop: 2 }}>
                    Direct comparison of actual AI recommendation scores, crowd metrics, weather conditions, and travel times.
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <button onClick={clearComparison} style={styles.clearFiltersBtn}>
                    Clear All
                  </button>
                  <button id="close-comparison-modal-btn" onClick={() => setIsComparisonOpen(false)} style={styles.closeModalBtn}>
                    ✕ Close
                  </button>
                </div>
              </div>

              {/* Comparison Matrix Table */}
              <div style={{ overflowX: 'auto', marginTop: 16 }}>
                <table style={styles.comparisonTable}>
                  <thead>
                    <tr>
                      <th style={styles.compTableHeaderAttr}>Attribute</th>
                      {comparedDestinationObjects.map((d) => (
                        <th key={d.place} style={styles.compTableHeaderDest}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                            <span style={{ fontSize: 16, fontWeight: 800, color: '#0f172a' }}>{d.place}</span>
                            <button
                              onClick={() => toggleComparison(d.place)}
                              style={styles.removeCompColBtn}
                              title={`Remove ${d.place}`}
                              aria-label={`Remove ${d.place} from comparison`}
                            >
                              ✕
                            </button>
                          </div>
                          <img
                            src={getPlaceImage(d.place, d.image)}
                            alt={d.place}
                            style={styles.compDestImg}
                          />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {/* Row 1: Recommendation Score */}
                    <tr>
                      <td style={styles.compAttrCell}>
                        <strong>Recommendation Score</strong>
                        <div style={{ fontSize: 11, color: '#64748b' }}>Overall score (0–100 scale)</div>
                      </td>
                      {comparedDestinationObjects.map((d) => (
                        <td key={d.place} style={styles.compValCell}>
                          <span style={styles.compScoreValue}>
                            {d.score != null ? `${d.score} / 100` : 'Not available'}
                          </span>
                        </td>
                      ))}
                    </tr>

                    {/* Row 2: Recommendation Decision */}
                    <tr>
                      <td style={styles.compAttrCell}>
                        <strong>Decision Level</strong>
                      </td>
                      {comparedDestinationObjects.map((d) => (
                        <td key={d.place} style={styles.compValCell}>
                          <span style={styles.compDecisionBadge}>
                            {d.ai_recommendation?.decision || 'Not available'}
                          </span>
                        </td>
                      ))}
                    </tr>

                    {/* Row 3: Crowd Density */}
                    <tr>
                      <td style={styles.compAttrCell}>
                        <strong>Crowd Density</strong>
                        <div style={{ fontSize: 11, color: '#64748b' }}>Predicted visitor metric</div>
                      </td>
                      {comparedDestinationObjects.map((d) => (
                        <td key={d.place} style={styles.compValCell}>
                          <strong>{d.crowd_label || d.crowd_safety?.crowd_level || 'Not available'}</strong>
                          {d.crowd != null && (
                            <div style={{ fontSize: 12, color: '#64748b' }}>Metric: {d.crowd}</div>
                          )}
                        </td>
                      ))}
                    </tr>

                    {/* Row 4: Weather Conditions */}
                    <tr>
                      <td style={styles.compAttrCell}>
                        <strong>Weather conditions</strong>
                        <div style={{ fontSize: 11, color: '#64748b' }}>API supplied conditions</div>
                      </td>
                      {comparedDestinationObjects.map((d) => (
                        <td key={d.place} style={styles.compValCell}>
                          <strong>{d.weather || d.weather_suitability?.condition || 'Not available'}</strong>
                          {d.weather_suitability?.temperature_c != null && (
                            <div style={{ fontSize: 12, color: '#64748b' }}>
                              🌡️ {d.weather_suitability.temperature_c}°C
                              {d.weather_suitability.rainfall_mm != null
                                ? ` • 🌧️ ${d.weather_suitability.rainfall_mm} mm`
                                : ''}
                            </div>
                          )}
                          {(d.weather_suitability?.timestamp || d.weather_timestamp) && (
                            <div style={{ fontSize: 11, color: '#475569', marginTop: 2 }}>
                              Observed: {d.weather_suitability?.timestamp || d.weather_timestamp}
                            </div>
                          )}
                        </td>
                      ))}
                    </tr>

                    {/* Row 5: Travel Distance & Duration */}
                    <tr>
                      <td style={styles.compAttrCell}>
                        <strong>Travel from Colombo</strong>
                      </td>
                      {comparedDestinationObjects.map((d) => (
                        <td key={d.place} style={styles.compValCell}>
                          <strong>
                            {d.travel_transport?.distance_km != null
                              ? `${d.travel_transport.distance_km} km`
                              : 'Not available'}
                          </strong>
                          <div style={{ fontSize: 12, color: '#64748b' }}>
                            ⏱ {d.travel_transport?.estimated_travel_time || 'Not available'}
                          </div>
                        </td>
                      ))}
                    </tr>

                    {/* Row 6: Top Activity */}
                    <tr>
                      <td style={styles.compAttrCell}>
                        <strong>Top Recommended Activity</strong>
                      </td>
                      {comparedDestinationObjects.map((d) => (
                        <td key={d.place} style={styles.compValCell}>
                          <strong>{d.activity_recommendations?.top_activity?.name || 'Not available'}</strong>
                          {d.activity_recommendations?.top_activity?.duration_hours != null && (
                            <div style={{ fontSize: 12, color: '#64748b' }}>
                              Duration: {d.activity_recommendations.top_activity.duration_hours}h
                            </div>
                          )}
                        </td>
                      ))}
                    </tr>

                    {/* Row 7: Optimal Activity Time */}
                    <tr>
                      <td style={styles.compAttrCell}>
                        <strong>Optimal Activity Window</strong>
                      </td>
                      {comparedDestinationObjects.map((d) => (
                        <td key={d.place} style={styles.compValCell}>
                          {d.event_timing?.best_activity_time ? (
                            <span>
                              {d.event_timing.best_activity_time} ({d.event_timing.best_time_period || 'standard'})
                            </span>
                          ) : (
                            'Not available'
                          )}
                        </td>
                      ))}
                    </tr>

                    {/* Row 8: Safety Profile */}
                    <tr>
                      <td style={styles.compAttrCell}>
                        <strong>Safety Rating</strong>
                      </td>
                      {comparedDestinationObjects.map((d) => (
                        <td key={d.place} style={styles.compValCell}>
                          {d.crowd_safety?.safety_level || 'Not available'}
                        </td>
                      ))}
                    </tr>

                    {/* Row 9: Why Recommended */}
                    <tr>
                      <td style={styles.compAttrCell}>
                        <strong>Why Recommended</strong>
                      </td>
                      {comparedDestinationObjects.map((d) => (
                        <td key={d.place} style={styles.compValCell}>
                          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: '#166534' }}>
                            {(d.ai_recommendation?.why_recommended || []).map((r, rIdx) => (
                              <li key={rIdx}>{r}</li>
                            ))}
                          </ul>
                        </td>
                      ))}
                    </tr>

                    {/* Row 10: Trade-offs */}
                    <tr>
                      <td style={styles.compAttrCell}>
                        <strong>Things to Consider</strong>
                      </td>
                      {comparedDestinationObjects.map((d) => (
                        <td key={d.place} style={styles.compValCell}>
                          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: '#92400e' }}>
                            {(d.ai_recommendation?.tradeoffs || []).map((t, tIdx) => (
                              <li key={tIdx}>{t}</li>
                            ))}
                          </ul>
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Complete Component Stylesheet ──
const styles = {
  container: {
    minHeight: '100vh',
    background: '#f8fafc',
    fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
    color: '#0f172a',
    paddingBottom: '80px',
  },

  exploreNavHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '16px 40px',
    background: '#ffffff',
    borderBottom: '1px solid #e2e8f0',
    position: 'sticky',
    top: 0,
    zIndex: 100,
  },

  backNavBtn: {
    padding: '8px 16px',
    borderRadius: '10px',
    border: '1px solid #cbd5e1',
    background: '#ffffff',
    color: '#334155',
    fontWeight: '600',
    fontSize: '13px',
    cursor: 'pointer',
  },

  cardIconBadge: {
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },

  recsMainContainer: {
    maxWidth: '1100px',
    margin: '28px auto',
    padding: '0 24px',
  },

  recsTitle: {
    fontSize: '28px',
    fontWeight: '800',
    color: '#0f172a',
    margin: '0 0 6px 0',
    letterSpacing: '-0.02em',
  },

  recsSubtitle: {
    fontSize: '14.5px',
    color: '#64748b',
    margin: 0,
  },

  topControlCard: {
    background: '#ffffff',
    borderRadius: '20px',
    border: '1px solid #e2e8f0',
    padding: '22px 24px',
    boxShadow: '0 8px 24px rgba(0,0,0,0.03)',
  },

  controlLabel: {
    fontSize: '12px',
    fontWeight: '700',
    color: '#334155',
    display: 'block',
    marginBottom: '6px',
  },

  inputIconWrapper: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    background: '#f8fafc',
    border: '1.5px solid #cbd5e1',
    borderRadius: '10px',
    padding: '0 12px',
    height: '42px',
  },

  prefInputWithIcon: {
    width: '100%',
    border: 'none',
    background: 'transparent',
    fontSize: '13.5px',
    color: '#0f172a',
    outline: 'none',
  },

  selectControl: {
    width: '100%',
    height: '42px',
    padding: '0 10px',
    borderRadius: '10px',
    border: '1.5px solid #cbd5e1',
    background: '#f8fafc',
    fontSize: '13px',
    fontWeight: '600',
    color: '#0f172a',
    outline: 'none',
    cursor: 'pointer',
  },

  dateInputControl: {
    width: '100%',
    boxSizing: 'border-box',
    height: '42px',
    padding: '0 10px',
    borderRadius: '10px',
    border: '1.5px solid #cbd5e1',
    background: '#f8fafc',
    fontSize: '13px',
    color: '#0f172a',
    outline: 'none',
    cursor: 'pointer',
  },

  mainActionBtn: {
    height: '42px',
    padding: '0 20px',
    borderRadius: '10px',
    border: 'none',
    background: '#059669',
    color: '#ffffff',
    fontWeight: '700',
    fontSize: '13.5px',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    boxShadow: '0 4px 14px rgba(5,150,105,0.25)',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },

  controlChipBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '5px 12px',
    borderRadius: '16px',
    border: '1px solid #a7f3d0',
    background: '#ecfdf5',
    color: '#047857',
    fontSize: '12px',
    fontWeight: '600',
    cursor: 'pointer',
  },

  errorBox: {
    marginTop: '20px',
    padding: '16px 20px',
    borderRadius: '14px',
    background: '#fef2f2',
    border: '1px solid #fecaca',
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
  },

  retryBtn: {
    padding: '8px 16px',
    borderRadius: '8px',
    border: '1px solid #b91c1c',
    background: '#ffffff',
    color: '#991b1b',
    fontWeight: '700',
    fontSize: '12.5px',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },

  loadingBox: {
    marginTop: '28px',
    padding: '48px 24px',
    textAlign: 'center',
    background: '#ffffff',
    borderRadius: '20px',
    border: '1px solid #e2e8f0',
  },

  emptyInitialCard: {
    marginTop: '28px',
    padding: '48px 24px',
    textAlign: 'center',
    background: '#ffffff',
    borderRadius: '20px',
    border: '1px dashed #cbd5e1',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
  },

  /* Primary Route Hero Card */
  routeHeroCard: {
    marginTop: '28px',
    background: '#ffffff',
    borderRadius: '24px',
    border: '2px solid #10b981',
    padding: '30px',
    boxShadow: '0 20px 40px rgba(16,185,129,0.08)',
  },

  routeHeroHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '14px',
    flexWrap: 'wrap',
    gap: '10px',
  },

  trophyBadge: {
    background: '#10b981',
    color: '#ffffff',
    padding: '6px 14px',
    borderRadius: '20px',
    fontSize: '12.5px',
    fontWeight: '800',
  },

  rankDecisionBadge: {
    background: '#ecfdf5',
    color: '#047857',
    border: '1px solid #a7f3d0',
    padding: '6px 14px',
    borderRadius: '20px',
    fontSize: '12.5px',
    fontWeight: '700',
  },

  routeSourceBadge: {
    background: '#f1f5f9',
    color: '#475569',
    border: '1px solid #cbd5e1',
    padding: '4px 10px',
    borderRadius: '12px',
    fontSize: '11px',
    fontWeight: '600',
  },

  routeScoreBox: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-end',
    background: '#f0fdf4',
    padding: '6px 16px',
    borderRadius: '14px',
    border: '1px solid #bbf7d0',
  },

  routeScoreNum: {
    fontSize: '28px',
    fontWeight: '900',
    color: '#059669',
  },

  routeScoreMax: {
    fontSize: '13px',
    color: '#94a3b8',
    fontWeight: '600',
  },

  routeSequenceTitle: {
    fontSize: '24px',
    fontWeight: '900',
    color: '#0f172a',
    margin: '0 0 10px 0',
    letterSpacing: '-0.02em',
  },

  routeDisclaimerNotice: {
    fontSize: '12px',
    color: '#64748b',
    background: '#f8fafc',
    padding: '8px 14px',
    borderRadius: '10px',
    border: '1px solid #e2e8f0',
    marginBottom: '18px',
  },

  statPillsRow: {
    display: 'flex',
    gap: '12px',
    flexWrap: 'wrap',
    marginBottom: '20px',
  },

  statPill: {
    padding: '7px 14px',
    borderRadius: '12px',
    background: '#f1f5f9',
    border: '1px solid #e2e8f0',
    fontSize: '13px',
    color: '#334155',
  },

  sectionDivider: {
    marginTop: '22px',
    paddingTop: '20px',
    borderTop: '1px solid #f1f5f9',
  },

  subSectionTitle: {
    fontSize: '15px',
    fontWeight: '800',
    color: '#0f172a',
    margin: '0 0 12px 0',
  },

  timelineContainer: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    overflowX: 'auto',
    padding: '14px 18px',
    background: '#f8fafc',
    borderRadius: '16px',
    border: '1px solid #e2e8f0',
  },

  timelineNode: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    background: '#ffffff',
    padding: '8px 16px',
    borderRadius: '12px',
    border: '1.5px solid #059669',
    boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
    whiteSpace: 'nowrap',
  },

  timelineDot: {
    width: '10px',
    height: '10px',
    borderRadius: '50%',
    background: '#10b981',
  },

  timelineNodeName: {
    fontSize: '13.5px',
    fontWeight: '700',
    color: '#0f172a',
  },

  timelineArrowRow: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '2px',
    whiteSpace: 'nowrap',
  },

  timelineLine: {
    width: '30px',
    height: '2px',
    background: '#cbd5e1',
  },

  segmentTimeBadge: {
    fontSize: '11px',
    fontWeight: '700',
    color: '#059669',
    background: '#ecfdf5',
    padding: '2px 8px',
    borderRadius: '8px',
  },

  segmentsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
    gap: '12px',
  },

  segmentCard: {
    background: '#f8fafc',
    borderRadius: '14px',
    border: '1px solid #e2e8f0',
    padding: '12px 14px',
  },

  segmentHeader: {
    fontSize: '13.5px',
    fontWeight: '700',
    color: '#0f172a',
    marginBottom: '6px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },

  placeItem: {
    paddingBottom: '10px',
    borderBottom: '1px dashed #e2e8f0',
  },

  placeCategoryBadge: {
    fontSize: '10px',
    fontWeight: '600',
    background: '#e0f2fe',
    color: '#0369a1',
    padding: '2px 6px',
    borderRadius: '6px',
    whiteSpace: 'nowrap',
  },

  estimatedDistBadge: {
    fontSize: '10px',
    fontWeight: '600',
    background: '#fef3c7',
    color: '#b45309',
    padding: '2px 6px',
    borderRadius: '6px',
  },

  segmentMetricsRow: {
    display: 'flex',
    gap: '16px',
    fontSize: '12.5px',
    color: '#475569',
  },

  segmentWarningsBox: {
    marginTop: '6px',
    paddingTop: '6px',
    borderTop: '1px dashed #cbd5e1',
  },

  dailyPlanGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
    gap: '12px',
  },

  dailyPlanCard: {
    background: '#f8fafc',
    borderRadius: '16px',
    border: '1px solid #e2e8f0',
    padding: '16px 18px',
  },

  dayBadge: {
    fontSize: '11px',
    fontWeight: '800',
    color: '#059669',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom: '4px',
  },

  dayRouteHeader: {
    fontSize: '14.5px',
    fontWeight: '800',
    color: '#0f172a',
    marginBottom: '4px',
  },

  activityItem: {
    fontSize: '12px',
    color: '#334155',
    background: '#ffffff',
    padding: '6px 10px',
    borderRadius: '8px',
    border: '1px solid #e2e8f0',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },

  reasonsCard: {
    background: '#f0fdf4',
    borderRadius: '16px',
    border: '1px solid #bbf7d0',
    padding: '18px',
  },

  tradeoffsCard: {
    background: '#fffbeb',
    borderRadius: '16px',
    border: '1px solid #fef3c7',
    padding: '18px',
  },

  cardSubHeader: {
    fontSize: '14px',
    fontWeight: '800',
    margin: '0 0 10px 0',
  },

  bulletList: {
    margin: 0,
    paddingLeft: 0,
    listStyle: 'none',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },

  whyListItem: {
    fontSize: '12.5px',
    color: '#166534',
    display: 'flex',
    alignItems: 'baseline',
    gap: '8px',
  },

  tradeoffListItem: {
    fontSize: '12.5px',
    color: '#92400e',
    display: 'flex',
    alignItems: 'baseline',
    gap: '8px',
  },

  /* ── Filter Controls Bar Styles ── */
  countBadge: {
    fontSize: '12px',
    fontWeight: '700',
    color: '#2563eb',
    background: '#eff6ff',
    padding: '3px 10px',
    borderRadius: '12px',
    border: '1px solid #bfdbfe',
  },

  filterActivePill: {
    fontSize: '11px',
    fontWeight: '800',
    color: '#b45309',
    background: '#fef3c7',
    padding: '3px 8px',
    borderRadius: '10px',
    border: '1px solid #fde68a',
  },

  clearFiltersBtn: {
    background: '#f1f5f9',
    border: '1px solid #cbd5e1',
    borderRadius: '8px',
    color: '#475569',
    fontSize: '12px',
    fontWeight: '700',
    padding: '6px 12px',
    cursor: 'pointer',
  },

  filterToggleBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '6px 12px',
    borderRadius: '8px',
    border: '1px solid #cbd5e1',
    fontSize: '12.5px',
    fontWeight: '700',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
  },

  activeFiltersBar: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '12px',
    padding: '8px 14px',
    marginBottom: '12px',
    flexWrap: 'wrap',
  },

  activeFilterPill: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    background: '#eff6ff',
    color: '#1e40af',
    border: '1px solid #bfdbfe',
    borderRadius: '14px',
    padding: '3px 9px',
    fontSize: '11.5px',
    fontWeight: '600',
  },

  removeActiveFilterBtn: {
    background: 'transparent',
    border: 'none',
    color: '#3b82f6',
    fontSize: '11px',
    cursor: 'pointer',
    padding: 0,
    lineHeight: 1,
    fontWeight: '700',
  },

  filterControlsPanel: {
    background: '#ffffff',
    borderRadius: '18px',
    border: '1px solid #e2e8f0',
    padding: '18px 20px',
    boxShadow: '0 4px 14px rgba(0,0,0,0.02)',
    marginBottom: '18px',
  },

  filterSectionTitle: {
    fontSize: '12px',
    fontWeight: '800',
    color: '#1e293b',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },

  filterHelpText: {
    fontSize: '11px',
    fontWeight: '400',
    color: '#64748b',
  },

  categoryChip: {
    padding: '6px 12px',
    borderRadius: '20px',
    border: '1px solid #cbd5e1',
    fontSize: '12px',
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    transition: 'all 0.15s ease',
  },

  filterToggleCard: {
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '12px',
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
  },

  filterSelect: {
    height: '34px',
    padding: '0 8px',
    borderRadius: '8px',
    border: '1px solid #cbd5e1',
    background: '#ffffff',
    fontSize: '12px',
    fontWeight: '600',
    color: '#0f172a',
    outline: 'none',
    cursor: 'pointer',
  },

  excludedSection: {
    marginTop: '14px',
    paddingTop: '12px',
    borderTop: '1px dashed #e2e8f0',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    flexWrap: 'wrap',
  },

  excludedChip: {
    background: '#fee2e2',
    color: '#991b1b',
    fontSize: '11.5px',
    fontWeight: '700',
    padding: '3px 8px',
    borderRadius: '12px',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    border: '1px solid #fecaca',
  },

  unexcludeBtn: {
    background: 'transparent',
    border: 'none',
    color: '#991b1b',
    fontSize: '11px',
    cursor: 'pointer',
    padding: 0,
    lineHeight: 1,
  },

  restoreAllBtn: {
    background: 'transparent',
    border: 'none',
    color: '#2563eb',
    fontSize: '11.5px',
    fontWeight: '700',
    cursor: 'pointer',
    textDecoration: 'underline',
  },

  emptyFilteredBox: {
    padding: '40px 20px',
    textAlign: 'center',
    background: '#ffffff',
    borderRadius: '16px',
    border: '1px dashed #cbd5e1',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
  },

  /* ── Destination Cards ── */
  recItemCard: {
    background: '#ffffff',
    borderRadius: '18px',
    border: '1px solid #e2e8f0',
    padding: '16px 20px',
    display: 'flex',
    alignItems: 'flex-start',
    gap: '18px',
    boxShadow: '0 4px 16px rgba(0,0,0,0.02)',
    transition: 'transform 0.15s ease',
  },

  recImageContainer: {
    position: 'relative',
    width: '140px',
    height: '95px',
    borderRadius: '14px',
    overflow: 'hidden',
    flexShrink: 0,
  },

  recImage: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
  },

  rankBadge: {
    position: 'absolute',
    top: '8px',
    left: '8px',
    padding: '2px 8px',
    borderRadius: '10px',
    color: '#ffffff',
    fontSize: '11px',
    fontWeight: '800',
    boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
  },

  recInfoCol: {
    flex: 1,
    minWidth: 0,
  },

  recPlaceTitle: {
    fontSize: '17px',
    fontWeight: '800',
    color: '#0f172a',
    margin: 0,
  },

  recPlaceDesc: {
    fontSize: '12.5px',
    color: '#64748b',
    margin: '4px 0 0 0',
    lineHeight: '1.4',
  },

  iconActionBtn: {
    fontSize: '11px',
    fontWeight: '700',
    padding: '4px 9px',
    borderRadius: '8px',
    border: '1px solid',
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
  },

  excludeIconBtn: {
    width: '26px',
    height: '26px',
    borderRadius: '50%',
    border: '1px solid #e2e8f0',
    background: '#f8fafc',
    color: '#94a3b8',
    cursor: 'pointer',
    fontSize: '12px',
    fontWeight: '700',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },

  subPill: {
    fontSize: '11.5px',
    color: '#475569',
    background: '#f1f5f9',
    padding: '3px 8px',
    borderRadius: '6px',
    fontWeight: '500',
  },

  cardScorePill: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '3px',
    background: '#f0fdf4',
    color: '#166534',
    border: '1px solid #bbf7d0',
    padding: '2px 8px',
    borderRadius: '8px',
    fontSize: '11.5px',
    fontWeight: '600',
  },

  cardDetailsDisclosure: {
    marginTop: '6px',
    borderTop: '1px solid #f1f5f9',
    paddingTop: '6px',
  },

  cardDetailsSummary: {
    fontSize: '11.5px',
    fontWeight: '700',
    color: '#2563eb',
    cursor: 'pointer',
    userSelect: 'none',
    padding: '2px 0',
  },

  cardDetailsContent: {
    marginTop: '6px',
    padding: '10px 12px',
    background: '#f8fafc',
    borderRadius: '10px',
    border: '1px solid #e2e8f0',
  },

  toggleActivitiesBtn: {
    background: 'none',
    border: 'none',
    color: '#2563eb',
    fontSize: '11.5px',
    fontWeight: '700',
    cursor: 'pointer',
    padding: 0,
    marginTop: '4px',
  },

  expandedActivitiesBox: {
    marginTop: '8px',
    padding: '12px',
    background: '#f8fafc',
    borderRadius: '12px',
    border: '1px solid #e2e8f0',
  },

  miniActivityCard: {
    background: '#ffffff',
    padding: '8px 10px',
    borderRadius: '8px',
    border: '1px solid #e2e8f0',
    fontSize: '12px',
  },

  miniCatTag: {
    fontSize: '10px',
    color: '#059669',
    background: '#ecfdf5',
    padding: '1px 5px',
    borderRadius: '4px',
    fontWeight: '600',
  },

  scoreCol: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-end',
    flexShrink: 0,
    paddingLeft: '16px',
    borderLeft: '1px solid #f1f5f9',
  },

  scoreValue: {
    fontSize: '24px',
    fontWeight: '900',
    color: '#059669',
  },

  scoreMax: {
    fontSize: '12px',
    fontWeight: '500',
    color: '#94a3b8',
  },

  /* ── Comparison Dock Bar ── */
  comparisonDockBar: {
    position: 'fixed',
    bottom: '20px',
    left: '50%',
    transform: 'translateX(-50%)',
    width: 'calc(100% - 48px)',
    maxWidth: '1050px',
    background: '#0f172a',
    borderRadius: '16px',
    padding: '12px 20px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    boxShadow: '0 12px 36px rgba(0,0,0,0.25)',
    zIndex: 900,
    flexWrap: 'wrap',
    gap: '12px',
  },

  compareMiniChip: {
    background: '#1e293b',
    color: '#f8fafc',
    fontSize: '12px',
    fontWeight: '700',
    padding: '4px 10px',
    borderRadius: '12px',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    border: '1px solid #334155',
  },

  removeCompareMiniBtn: {
    background: 'transparent',
    border: 'none',
    color: '#94a3b8',
    cursor: 'pointer',
    padding: 0,
    fontSize: '11px',
    lineHeight: 1,
  },

  openCompareBtn: {
    background: '#2563eb',
    color: '#ffffff',
    border: 'none',
    borderRadius: '10px',
    padding: '8px 16px',
    fontSize: '12.5px',
    fontWeight: '700',
    cursor: 'pointer',
    boxShadow: '0 4px 12px rgba(37,99,235,0.3)',
  },

  clearCompareBtn: {
    background: 'transparent',
    border: '1px solid #475569',
    color: '#cbd5e1',
    borderRadius: '10px',
    padding: '7px 12px',
    fontSize: '12px',
    fontWeight: '600',
    cursor: 'pointer',
  },

  /* ── Comparison Modal ── */
  modalBackdrop: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(15, 23, 42, 0.75)',
    backdropFilter: 'blur(6px)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
    padding: '20px',
  },

  modalContainer: {
    background: '#ffffff',
    borderRadius: '24px',
    width: '100%',
    maxWidth: '1000px',
    maxHeight: '90vh',
    overflowY: 'auto',
    padding: '28px',
    boxShadow: '0 24px 60px rgba(0,0,0,0.2)',
  },

  modalHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    paddingBottom: '16px',
    borderBottom: '1px solid #e2e8f0',
  },

  closeModalBtn: {
    background: '#f1f5f9',
    border: '1px solid #cbd5e1',
    borderRadius: '8px',
    color: '#0f172a',
    fontSize: '13px',
    fontWeight: '700',
    padding: '6px 14px',
    cursor: 'pointer',
  },

  comparisonTable: {
    width: '100%',
    borderCollapse: 'collapse',
    textAlign: 'left',
  },

  compTableHeaderAttr: {
    width: '28%',
    padding: '12px 14px',
    fontSize: '13px',
    fontWeight: '800',
    color: '#475569',
    background: '#f8fafc',
    borderBottom: '2px solid #cbd5e1',
  },

  compTableHeaderDest: {
    padding: '12px 14px',
    borderBottom: '2px solid #cbd5e1',
    verticalAlign: 'top',
  },

  compDestImg: {
    width: '100%',
    height: '90px',
    objectFit: 'cover',
    borderRadius: '10px',
    marginTop: '8px',
  },

  removeCompColBtn: {
    background: '#f1f5f9',
    border: '1px solid #cbd5e1',
    borderRadius: '50%',
    width: '20px',
    height: '20px',
    fontSize: '10px',
    color: '#64748b',
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
  },

  compAttrCell: {
    padding: '12px 14px',
    borderBottom: '1px solid #f1f5f9',
    fontSize: '12.5px',
    color: '#334155',
    verticalAlign: 'top',
    background: '#fcfcfc',
  },

  compValCell: {
    padding: '12px 14px',
    borderBottom: '1px solid #f1f5f9',
    fontSize: '12.5px',
    color: '#0f172a',
    verticalAlign: 'top',
  },

  compScoreValue: {
    fontSize: '18px',
    fontWeight: '900',
    color: '#059669',
  },

  compDecisionBadge: {
    fontSize: '11px',
    fontWeight: '800',
    padding: '3px 8px',
    borderRadius: '8px',
    background: '#ecfdf5',
    color: '#047857',
  },

  // Weather Advisory Panel Styles
  weatherPanelCard: {
    background: '#ffffff',
    borderRadius: '16px',
    border: '1px solid #bfdbfe',
    boxShadow: '0 4px 16px rgba(37, 99, 235, 0.08)',
    padding: '20px 24px',
    marginTop: '28px',
    marginBottom: '28px',
  },
  weatherPanelHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: '12px',
    borderBottom: '1px solid #e2e8f0',
    paddingBottom: '14px',
  },
  weatherPanelTitle: {
    fontSize: '18px',
    fontWeight: '800',
    color: '#0f172a',
    margin: 0,
  },
  weatherDestSelect: {
    padding: '6px 10px',
    borderRadius: '8px',
    border: '1px solid #cbd5e1',
    background: '#ffffff',
    fontSize: '13px',
    fontWeight: '600',
    color: '#0f172a',
    cursor: 'pointer',
    outline: 'none',
  },
  weatherRefreshBtn: {
    padding: '6px 12px',
    borderRadius: '8px',
    border: '1px solid #0284c7',
    background: '#f0f9ff',
    color: '#0284c7',
    fontSize: '12.5px',
    fontWeight: '700',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
  },
  weatherQuickChip: {
    padding: '4px 10px',
    borderRadius: '14px',
    border: 'none',
    fontSize: '11.5px',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
  },
  weatherScopeNotice: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '10px',
    background: '#eff6ff',
    border: '1px solid #bfdbfe',
    borderRadius: '10px',
    padding: '10px 14px',
    marginTop: '12px',
    color: '#1e3a8a',
  },
  weatherDestSwitchLoading: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '12px',
    padding: '24px 20px',
    marginTop: '14px',
  },
  weatherStaleBanner: {
    background: '#fff7ed',
    border: '1px solid #fed7aa',
    borderRadius: '8px',
    padding: '8px 12px',
    fontSize: '12px',
    color: '#9a3412',
    marginTop: '10px',
  },
  weatherErrorBanner: {
    background: '#fef2f2',
    border: '1px solid #fecaca',
    borderRadius: '8px',
    padding: '10px 14px',
    fontSize: '12.5px',
    color: '#991b1b',
    marginTop: '12px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  retryWeatherBtn: {
    padding: '4px 10px',
    borderRadius: '6px',
    border: '1px solid #ef4444',
    background: '#ffffff',
    color: '#b91c1c',
    fontSize: '11.5px',
    fontWeight: '700',
    cursor: 'pointer',
  },
  weatherStatusBar: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: '8px',
    background: '#f8fafc',
    padding: '8px 12px',
    borderRadius: '8px',
    border: '1px solid #f1f5f9',
  },
  validTimePill: {
    fontSize: '11.5px',
    color: '#475569',
  },
  weatherAdvisoryCallout: {
    display: 'flex',
    gap: '14px',
    alignItems: 'flex-start',
    padding: '14px 16px',
    borderRadius: '12px',
    border: '1px solid',
    marginTop: '12px',
  },
  advisoryDisclaimers: {
    marginTop: '8px',
    paddingTop: '8px',
    borderTop: '1px solid rgba(0,0,0,0.06)',
    fontSize: '11.5px',
    color: '#475569',
  },
  subCardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    fontSize: '13px',
    fontWeight: '700',
    color: '#1e293b',
    marginBottom: '8px',
  },
  currentMetricsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
    gap: '10px',
  },
  metricItem: {
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '10px',
    padding: '10px 12px',
  },
  metricLabel: {
    fontSize: '11px',
    fontWeight: '700',
    color: '#64748b',
    textTransform: 'uppercase',
    letterSpacing: '0.03em',
  },
  metricValue: {
    fontSize: '16px',
    fontWeight: '800',
    color: '#0f172a',
    margin: '3px 0',
  },
  forecastUnavailableNotice: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '10px',
    padding: '12px 14px',
    color: '#475569',
    fontSize: '12.5px',
  },
  hourlyScrollStrip: {
    display: 'flex',
    gap: '8px',
    overflowX: 'auto',
    paddingBottom: '8px',
  },
  hourlyPillCard: {
    flexShrink: 0,
    width: '84px',
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: '10px',
    padding: '8px 6px',
    textAlign: 'center',
  },
  weatherAttributionFooter: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: '8px',
    marginTop: '14px',
    paddingTop: '10px',
    borderTop: '1px solid #f1f5f9',
    fontSize: '11px',
    color: '#64748b',
  },
  routeWeatherSummaryBox: {
    display: 'flex',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: '8px',
    marginTop: '12px',
  },
  forecastRangeHint: {
    marginTop: '10px',
    fontSize: '11.5px',
    color: '#92400e',
    background: '#fffbeb',
    border: '1px solid #fde68a',
    borderRadius: '6px',
    padding: '6px 10px',
  },
  routeStopWeatherChip: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    background: '#f0f9ff',
    border: '1px solid #bae6fd',
    borderRadius: '999px',
    padding: '4px 12px',
    fontSize: '12.5px',
    color: '#0f172a',
  },
  weatherDetailsDisclosure: {
    marginTop: '14px',
    borderTop: '1px solid #e2e8f0',
    paddingTop: '10px',
  },
  weatherDetailsSummary: {
    fontSize: '12.5px',
    fontWeight: '700',
    color: '#2563eb',
    cursor: 'pointer',
    userSelect: 'none',
    padding: '4px 0',
  },
  weatherDetailsBody: {
    marginTop: '10px',
    padding: '14px',
    background: '#f8fafc',
    borderRadius: '12px',
    border: '1px solid #e2e8f0',
  },
};
