/**
 * Test Suite: Weather Advisory Semantics, Query Detection & Fixture Interpretations
 * Executed outside of the normal application UI.
 */
import {
  WMO_WEATHER_CODES,
  getWmoWeatherInfo,
  generateWeatherAdvisory,
  getRelevantHourlyForecast,
  detectDestinationFromQuery,
  FIXTURES_FOR_TESTING,
} from './weatherService.js';

let passed = 0;
let failed = 0;

function assert(condition, message) {
  if (condition) {
    passed++;
    console.log(`  ✓ ${message}`);
  } else {
    failed++;
    console.error(`  ✗ FAIL: ${message}`);
  }
}

console.log('--- 1. Testing Query-Based Destination Detection ---');
{
  const kandyQuery = detectDestinationFromQuery('I would love to visit Kandy for temple and cultural tours');
  assert(kandyQuery.isUnambiguous === true, 'Kandy query detected as unambiguous');
  assert(kandyQuery.detected === 'Kandy', 'Canonical destination "Kandy" detected');

  const multiQuery = detectDestinationFromQuery('Trip from Kandy to Galle and Ella');
  assert(multiQuery.isUnambiguous === false, 'Multi-destination query not marked unambiguous');
  assert(multiQuery.reason === 'multi_destination', 'Reason identified as multi_destination');
  assert(multiQuery.matches.length === 3, 'Matches all 3 mentioned destinations');

  const genericQuery = detectDestinationFromQuery('I want quiet sandy beaches and wildlife');
  assert(genericQuery.isUnambiguous === false, 'Generic interest query has no destination');
  assert(genericQuery.detected === null, 'Detected is null for generic query');

  const nuwaraEliyaQuery = detectDestinationFromQuery('Hiking around Nuwara Eliya tea estates');
  assert(nuwaraEliyaQuery.isUnambiguous === true, 'Nuwara Eliya detected');
  assert(nuwaraEliyaQuery.detected === 'Nuwara Eliya', 'Canonical "Nuwara Eliya" detected');
}

console.log('\n--- 2. Testing WMO Code Semantics (Open-Meteo Documentation) ---');
{
  // Code 95: Thunderstorm: Slight or moderate
  const code95 = WMO_WEATHER_CODES[95];
  assert(code95.description.includes('Thunderstorm'), 'Code 95 is described as Thunderstorm');
  assert(!code95.description.toLowerCase().includes('hail'), 'Code 95 does NOT mention hail in description');
  assert(!code95.advisory.toLowerCase().includes('hail'), 'Code 95 advisory does NOT assert hail');

  // Codes 96 & 99: Hail
  const code96 = WMO_WEATHER_CODES[96];
  assert(code96.description.toLowerCase().includes('hail'), 'Code 96 description includes hail');
  const code99 = WMO_WEATHER_CODES[99];
  assert(code99.description.toLowerCase().includes('hail'), 'Code 99 description includes hail');

  // Unknown codes must not produce reassuring status
  const unknown = getWmoWeatherInfo(9999);
  assert(unknown.category === 'unknown', 'Unknown code marked as unknown category');
  assert(unknown.disruptionLevel === 'Unassessed (data incomplete)', 'Unknown code has unassessed disruption level');
  assert(!unknown.advisory.includes('Favorable'), 'Unknown code does not produce reassuring favorable status');
}

console.log('\n--- 3. Testing Adverse Weather Fixtures (Simulated Tests Outside Production UI) ---');
{
  // Severe Thunderstorm with Hail Fixture
  const hailAdv = generateWeatherAdvisory(FIXTURES_FOR_TESTING.severeThunderstormWithHail, null);
  assert(hailAdv.level === 'Caution', 'Hail fixture generates Caution level');
  assert(hailAdv.title.includes('Hail'), 'Hail advisory title mentions hail');
  assert(hailAdv.outdoorDisruption.includes('Severe Outdoor Disruption Potential'), 'Hail has Severe disruption');
  assert(hailAdv.officialWarningStatus === 'Not checked', 'Official warning status is strictly "Not checked"');
  assert(hailAdv.officialWarningNote.includes('No automated official-warning feed is integrated'), 'Contains exact note about automated feed');

  // Standard Thunderstorm (Code 95) with normal wind
  const tstormAdv = generateWeatherAdvisory(FIXTURES_FOR_TESTING.thunderstormStandard, null);
  assert(tstormAdv.level === 'Caution', 'Standard thunderstorm generates Caution level');
  assert(!tstormAdv.title.includes('Hail'), 'Standard thunderstorm does NOT mention hail in title');
  assert(!tstormAdv.message.includes('High wind speeds'), 'Standard thunderstorm with normal wind does not assert high wind');

  // Unknown Code Fixture
  const unknownAdv = generateWeatherAdvisory(FIXTURES_FOR_TESTING.unknownCode, null);
  assert(unknownAdv.title.includes('Unassessed'), 'Unknown code fixture produces Unassessed title');
  assert(unknownAdv.outdoorDisruption.includes('Unassessed'), 'Unknown code produces Unassessed disruption');
}

console.log('\n--- 4. Testing Date Coverage Semantics ---');
{
  const mockWeatherData = {
    current: { time: '2026-10-19T02:00' },
    hourly: [
      { dateStr: '2026-10-19', hourStr: '02:00', temperature: 20 },
      { dateStr: '2026-10-19', hourStr: '03:00', temperature: 19 },
      { dateStr: '2026-10-25', hourStr: '12:00', temperature: 25 },
    ],
  };

  const coveredToday = getRelevantHourlyForecast(mockWeatherData, '2026-10-19');
  assert(coveredToday.covered === true, 'Today is covered');
  assert(coveredToday.isToday === true, 'Flagged as today');

  const coveredFuture = getRelevantHourlyForecast(mockWeatherData, '2026-10-25');
  assert(coveredFuture.covered === true, 'Covered future date within forecast window');

  const uncovered = getRelevantHourlyForecast(mockWeatherData, '2026-12-25');
  assert(uncovered.covered === false, 'Uncovered date returns covered: false');
  assert(uncovered.message.includes("configured 7-day forecast window"), 'Described as application configured 7-day window');
}

console.log(`\n========================================`);
console.log(`Test Results: ${passed} Passed, ${failed} Failed`);
console.log(`========================================`);

if (failed > 0) {
  process.exit(1);
}
