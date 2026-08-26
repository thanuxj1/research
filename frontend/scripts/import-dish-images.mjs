/**
 * Copy the dish photos into `public/dishes/`, named after the dish.
 *
 *     node scripts/import-dish-images.mjs <source-directory> [--dry-run]
 *
 * Run once already; committed output lives in `public/dishes/`. It exists as a
 * script rather than as a one-off shell command because the naming rule is the
 * whole contract with the running app — `dishSlug()` from `src/lib/dishImage.js`
 * is imported here, not reimplemented — and because the next batch of photos
 * needs to land under the same rule. A rename in the CSV is fixed by re-running
 * this, then `npm run verify`.
 *
 * Matching is by slug, not by filename, so the source folder may name its files
 * however it likes as long as the words match. One relaxation on top of that: a
 * trailing parenthetical is dropped and the match retried, which is what pairs
 * `Mutton Curry (Lamb Curry).jpg` with the dish `Mutton Curry`. Exact matches are
 * taken first, so a dish whose own name carries a parenthetical - `Kiri Toffee
 * (Milk Toffee)` - still binds to the file that spells it out.
 *
 * Every ambiguity is a hard error rather than a warning. Two dishes collapsing to
 * one slug, or two files claiming one dish, would mean one dish silently wearing
 * another's photo, and a wrong photo is worse than a missing one: it is a claim
 * about the food that nothing downstream can detect.
 */

import { copyFileSync, existsSync, mkdirSync, readdirSync, statSync } from 'node:fs'
import { basename, extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { DISH_IMAGE_EXT, dishSlug } from '../src/lib/dishImage.js'
import { CSV_PATH, readDishNames } from './dishNames.mjs'

const DEST = fileURLToPath(new URL('../public/dishes', import.meta.url))

const args = process.argv.slice(2)
const dryRun = args.includes('--dry-run')
const source = args.find((arg) => !arg.startsWith('--'))

function die(message) {
  console.error(`\n${message}\n`)
  process.exit(1)
}

if (!source) die('usage: node scripts/import-dish-images.mjs <source-directory> [--dry-run]')
if (!existsSync(source) || !statSync(source).isDirectory()) die(`not a directory: ${source}`)

const names = readDishNames()
if (!names) die(`no dish list to match against: ${CSV_PATH} is missing`)

/* -- the dish side ------------------------------------------------------- */
const dishBySlug = new Map()
for (const name of names) {
  const slug = dishSlug(name)
  if (dishBySlug.has(slug)) {
    die(`slug collision: "${name}" and "${dishBySlug.get(slug)}" both slugify to "${slug}"`)
  }
  dishBySlug.set(slug, name)
}

/* -- the file side ------------------------------------------------------- */
/** `Mutton Curry (Lamb Curry)` -> `Mutton Curry`. Left alone if there is no tail. */
const withoutGloss = (stem) => stem.replace(/\s*\([^)]*\)\s*$/, '').trim()

const candidates = readdirSync(source)
  .filter((file) => extname(file).toLowerCase() === DISH_IMAGE_EXT)
  .sort()

const skipped = readdirSync(source).filter(
  (file) => extname(file).toLowerCase() !== DISH_IMAGE_EXT,
)

// Exact slugs first, then the gloss-stripped ones, so the fallback can never
// outrank a file that already spells the dish name exactly.
const claims = new Map() // dish slug -> source filename
const unmatched = []
for (const pass of ['exact', 'gloss']) {
  for (const file of candidates) {
    if ([...claims.values()].includes(file)) continue
    const stem = basename(file, extname(file))
    const slug = dishSlug(pass === 'exact' ? stem : withoutGloss(stem))
    if (!dishBySlug.has(slug)) {
      if (pass === 'gloss') unmatched.push(file)
      continue
    }
    if (claims.has(slug)) {
      die(`two files claim "${dishBySlug.get(slug)}": ${claims.get(slug)} and ${file}`)
    }
    claims.set(slug, file)
  }
}

/* -- report before writing ----------------------------------------------- */
const missing = [...dishBySlug].filter(([slug]) => !claims.has(slug)).map(([, name]) => name)

console.log(`\n${names.length} dishes, ${candidates.length} ${DISH_IMAGE_EXT} files in ${source}`)
if (skipped.length) console.log(`  ignored (not ${DISH_IMAGE_EXT}): ${skipped.join(', ')}`)
if (unmatched.length) {
  console.log(`  ${unmatched.length} file(s) matched no dish:`)
  for (const file of unmatched) console.log(`    ${file}`)
}
if (missing.length) {
  console.log(`  ${missing.length} dish(es) have no photo:`)
  for (const name of missing) console.log(`    ${name}`)
}

if (dryRun) {
  console.log(`\ndry run — would copy ${claims.size} file(s)\n`)
  process.exit(unmatched.length || missing.length ? 1 : 0)
}

mkdirSync(DEST, { recursive: true })
for (const [slug, file] of claims) {
  copyFileSync(join(source, file), join(DEST, slug + DISH_IMAGE_EXT))
}
console.log(`\ncopied ${claims.size} file(s) to public/dishes/\n`)

// Non-zero on any gap: partial coverage is the failure mode worth catching here,
// because a grid where some cards have photos reads as "this dish is broken"
// rather than as "we do not have a picture of this one".
process.exit(unmatched.length || missing.length ? 1 : 0)
