/**
 * Dish name -> photo file.
 *
 * The API carries no image field, and this is the reason it does not need one:
 * the client derives the path from the dish name, which is already the join key
 * shared by the CSV, the description table, the price table and the venue
 * profiles. Nothing has to be kept in sync on the server, and no card waits on a
 * second request to learn where its picture lives.
 *
 * The cost of deriving it is a claim the server cannot check — that a file
 * exists for every name. `npm run verify` checks it instead, in both directions:
 * a dish with no photo and a photo with no dish are both build failures. That is
 * the only reason it is safe to render `<img>` from a computed path without a
 * lookup table; without the check, renaming a dish in the CSV would silently
 * produce a broken tile.
 *
 * Deliberately free of React and of `import.meta`, so that `scripts/verify.mjs`
 * and `scripts/import-dish-images.mjs` can import this exact function under
 * plain Node. Sharing the one definition is what makes the build check and the
 * runtime provably agree instead of merely looking similar. The deploy-base
 * prefix therefore belongs to `DishImage.jsx`, not here.
 */

/** Directory under `public/`, and so also the URL prefix, holding the photos. */
export const DISH_IMAGE_DIR = 'dishes'

/** Every photo in the set is a JPEG; the importer refuses anything else. */
export const DISH_IMAGE_EXT = '.jpg'

/**
 * Filename-safe form of a dish name.
 *
 * Lowercased, with every run of non-alphanumerics collapsed to one hyphen, so
 * `Kesel Muwa Curry (Banana Blossom Curry)` becomes
 * `kesel-muwa-curry-banana-blossom-curry`. All 155 names are ASCII and yield 155
 * distinct slugs today; the importer fails loudly if two names ever collapse to
 * the same slug rather than letting one dish quietly overwrite another's photo.
 */
export function dishSlug(name) {
  return String(name)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

/** Path relative to the site root, e.g. `dishes/chicken-kottu.jpg`. */
export function dishImageFile(name) {
  return `${DISH_IMAGE_DIR}/${dishSlug(name)}${DISH_IMAGE_EXT}`
}
