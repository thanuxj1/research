/**
 * The dish names, read from the backend's CSV.
 *
 * Shared by `verify.mjs` and `import-dish-images.mjs` so the check and the
 * importer cannot disagree about what the set of dishes is. Resolved relative to
 * this file rather than to `process.cwd()`, so both scripts work from any
 * directory.
 *
 * Returns `null` — not an empty list — when the CSV is not there. A frontend
 * checked out without the backend is a legitimate state, and the callers treat it
 * as "cannot check" rather than as "no dishes exist", which would otherwise turn
 * every photo into an orphan and fail the build for the wrong reason.
 */

import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

export const CSV_PATH = fileURLToPath(
  new URL('../../backend/sri_lankan_food_dataset.csv', import.meta.url),
)

export function readDishNames() {
  if (!existsSync(CSV_PATH)) return null

  // Strip the BOM: the file is UTF-8 with one, and left in place it becomes part
  // of the header name and of the first dish's name.
  const raw = readFileSync(CSV_PATH, 'utf8').replace(/^﻿/, '')

  // `name` is the first column and the file has no quoted fields, so splitting on
  // the first comma is exact. Both facts are asserted rather than assumed: a name
  // that ever needed quoting would silently truncate here instead, and this is
  // the cheapest place to notice the format changed.
  if (raw.includes('"')) {
    throw new Error(`${CSV_PATH}: contains a quoted field; this reader cannot parse it`)
  }

  const lines = raw.split(/\r?\n/).filter((line) => line.trim() !== '')
  const header = lines[0].split(',')[0].trim()
  if (header !== 'name') {
    throw new Error(`${CSV_PATH}: expected the first column to be "name", found "${header}"`)
  }

  return lines.slice(1).map((line) => line.split(',')[0].trim())
}
