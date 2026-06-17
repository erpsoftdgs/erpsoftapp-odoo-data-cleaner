// Next.js does not prefix client-side fetch() calls or plain <a href> with
// basePath automatically (only <Link> and router.push() do). Any API call
// made from a Client Component or browser-rendered link must be prefixed
// with this constant, which must match next.config.ts's `basePath`.
export const BASE_PATH = "/dataconv";
