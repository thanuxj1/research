/**
 * Build-free static verification for the client.
 *
 * Checks, without needing `npm install`:
 *   1. every .js/.jsx file parses as JSX
 *   2. every relative import resolves to a real file
 *   3. every named import actually exists as an export in its target
 *   4. every literal className used in JSX is defined in the stylesheets
 *   5. every dish has a photo in public/, and every photo has a dish
 *
 * Run with Bun (uses Bun's built-in JSX transpiler for step 1):
 *     bun scripts/verify.mjs
 *
 * Under Node, step 1 falls back to `@babel/parser` when it can be resolved
 * (it arrives with @vitejs/plugin-react, so an installed tree has it), and is
 * skipped only when neither is available. Steps 2-5 always run.
 */

import { readdirSync, statSync, readFileSync, existsSync } from 'node:fs'
import { join, extname, dirname, resolve } from 'node:path'
import { createRequire } from 'node:module'
import { DISH_IMAGE_DIR, DISH_IMAGE_EXT, dishSlug } from '../src/lib/dishImage.js'
import { CSV_PATH, readDishNames } from './dishNames.mjs'

const SRC = 'src'
const STYLES = ['src/styles/theme.css', 'src/styles/components.css']
const RESOLVE_EXT = ['', '.js', '.jsx', '/index.js', '/index.jsx']

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) walk(path, out)
    else if (['.js', '.jsx'].includes(extname(path))) out.push(path)
  }
  return out
}

const files = walk(SRC).sort()
let failures = 0
const fail = (message) => {
  failures += 1
  console.log(`  ${message}`)
}

/* -- 1. parse ------------------------------------------------------------- */
console.log('\nparse')

/** Bun's transpiler, or a @babel/parser shim with the same throw-on-error shape. */
function loadParser() {
  if (typeof Bun !== 'undefined') {
    const transpiler = new Bun.Transpiler({ loader: 'jsx' })
    return { name: 'Bun', parse: (source) => transpiler.transformSync(source) }
  }
  try {
    const require = createRequire(import.meta.url)
    const { parse } = require('@babel/parser')
    return {
      name: '@babel/parser',
      parse: (source) => parse(source, { sourceType: 'module', plugins: ['jsx'] }),
    }
  } catch {
    // No installed tree. The remaining steps are the ones that catch the
    // mistakes this script exists for, so this is a warning, not a failure.
    return null
  }
}

const parser = loadParser()
if (parser) {
  const targets = [...files, 'vite.config.js']
  let ok = 0
  for (const file of targets) {
    try {
      parser.parse(readFileSync(file, 'utf8'))
      ok += 1
    } catch (error) {
      fail(`PARSE ${file}: ${String(error.message || error).split('\n')[0]}`)
    }
  }
  console.log(`  ${ok}/${targets.length} files parse as JSX (${parser.name})`)
} else {
  console.log('  skipped (needs Bun, or @babel/parser from an installed node_modules)')
}

/* -- 2 & 3. imports / exports -------------------------------------------- */
const exportsByFile = new Map()
for (const file of files) {
  const source = readFileSync(file, 'utf8')
  const names = new Set()
  for (const m of source.matchAll(
    /export\s+(?:async\s+)?(?:function|class|const|let|var)\s+([A-Za-z0-9_$]+)/g,
  )) {
    names.add(m[1])
  }
  for (const m of source.matchAll(/export\s*\{([^}]*)\}/g)) {
    for (const part of m[1].split(',')) {
      const bits = part.trim().split(/\s+as\s+/)
      const name = (bits[1] || bits[0] || '').trim()
      if (name) names.add(name)
    }
  }
  if (/export\s+default/.test(source)) names.add('default')
  exportsByFile.set(resolve(file), names)
}

console.log('\nimports')
const before = failures
for (const file of files) {
  const source = readFileSync(file, 'utf8')
  // Match every import, then filter to relative ones. Anchoring the regex on a
  // relative path lets the clause capture run backwards across the preceding
  // `import ... from 'react'` line and produce phantom failures.
  for (const m of source.matchAll(/import\s+([\s\S]*?)\s+from\s+['"]([^'"]+)['"]/g)) {
    const clause = m[1]
    const spec = m[2]
    if (!spec.startsWith('.')) continue

    if (/\.css$/.test(spec)) {
      if (!existsSync(resolve(dirname(file), spec))) fail(`MISSING CSS ${file} -> ${spec}`)
      continue
    }

    const base = resolve(dirname(file), spec)
    const target = RESOLVE_EXT.map((ext) => base + ext).find(
      (candidate) => existsSync(candidate) && statSync(candidate).isFile(),
    )
    if (!target) {
      fail(`UNRESOLVED ${file} -> ${spec}`)
      continue
    }

    const available = exportsByFile.get(resolve(target)) ?? new Set()
    const named = clause.match(/\{([^}]*)\}/)
    if (named) {
      for (const part of named[1].split(',')) {
        const name = part.trim().split(/\s+as\s+/)[0].trim()
        if (name && !available.has(name)) {
          fail(`NO EXPORT ${file} -> ${spec} needs "${name}"`)
        }
      }
    }
    const defaultImport = clause.replace(/\{[^}]*\}/, '').replace(/,/g, '').trim()
    if (defaultImport && !available.has('default')) {
      fail(`NO DEFAULT ${file} -> ${spec} (imported as ${defaultImport})`)
    }
  }
}
if (failures === before) console.log('  all relative imports resolve; all named imports exist')

/* -- 4. className coverage ----------------------------------------------- */
console.log('\nstyles')
const css = STYLES.map((file) => readFileSync(file, 'utf8')).join('\n')
const defined = new Set([...css.matchAll(/\.(-?[_a-zA-Z][\w-]*)/g)].map((m) => m[1]))

// Only literal string classNames are checked; anything interpolated is skipped.
const used = new Map()
for (const file of files) {
  const source = readFileSync(file, 'utf8')
  for (const m of source.matchAll(/className="([^"{}]+)"/g)) {
    for (const cls of m[1].split(/\s+/).filter(Boolean)) used.set(cls, file)
  }
  // Class strings inside className={[...].join(' ')} and template literals.
  for (const m of source.matchAll(/className=\{([\s\S]*?)\n\s*(?:>|\/>|[a-z-]+=)/g)) {
    for (const s of m[1].matchAll(/'([a-z][a-z0-9-]*(?:__|--)[a-z0-9-]+|[a-z]+--[a-z0-9-]+)'/g)) {
      used.set(s[1], file)
    }
  }
}
const undefinedClasses = [...used].filter(([cls]) => !defined.has(cls))
for (const [cls, file] of undefinedClasses) fail(`UNDEFINED .${cls} (used in ${file})`)
if (!undefinedClasses.length) {
  console.log(`  ${used.size} literal classNames all defined (${defined.size} selectors available)`)
}

/* -- 5. dish photos ------------------------------------------------------- */
/**
 * The client builds each card's `src` from the dish name (`src/lib/dishImage.js`)
 * instead of reading an image field off the API, which means nothing at runtime
 * can tell it that a file is missing — the browser just shows a hole. This is the
 * check that makes that trade safe, and it runs in both directions on purpose:
 *
 *   - a dish with no photo is the visible failure, and partial coverage is worse
 *     than none, because a grid where three cards out of twenty have no picture
 *     reads as "those dishes are broken" rather than as "we have no photo";
 *   - a photo with no dish is the invisible one. It means a dish was renamed in
 *     the CSV and the old file was left behind, so the *new* name is now
 *     unmatched and the stale file is quietly shipped to every visitor.
 *
 * Same `dishSlug` the app imports, not a copy of the rule, so this cannot pass
 * while the running client looks somewhere else.
 */
console.log('\ndish photos')
const dishNames = readDishNames()
const photoDir = join('public', DISH_IMAGE_DIR)

if (!dishNames) {
  // A frontend-only checkout is legitimate; treating it as "no dishes" would call
  // all 155 photos orphans and fail for entirely the wrong reason.
  console.log(`  skipped (no dish list at ${CSV_PATH})`)
} else if (!existsSync(photoDir)) {
  fail(`MISSING ${photoDir}/ — run: node scripts/import-dish-images.mjs <source-dir>`)
} else {
  const onDisk = new Set(readdirSync(photoDir))
  const wanted = new Map()
  for (const name of dishNames) wanted.set(dishSlug(name) + DISH_IMAGE_EXT, name)

  const missingPhotos = [...wanted].filter(([file]) => !onDisk.has(file))
  for (const [file, name] of missingPhotos) fail(`NO PHOTO ${name} -> ${photoDir}/${file}`)

  const orphans = [...onDisk].filter((file) => !wanted.has(file))
  for (const file of orphans) fail(`ORPHAN PHOTO ${photoDir}/${file} matches no dish`)

  if (!missingPhotos.length && !orphans.length) {
    console.log(`  ${wanted.size} dishes, ${wanted.size} photos, no orphans`)
  }
}

/* -- summary -------------------------------------------------------------- */
console.log(failures === 0 ? '\nOK — no problems found\n' : `\n${failures} problem(s)\n`)
process.exit(failures === 0 ? 0 : 1)
