/** Navigation policy for the app window: it may only show the local Next.js server. */

export function isSameOrigin(url: string, origin: string): boolean {
  try {
    return new URL(url).origin === new URL(origin).origin;
  } catch {
    return false;
  }
}

/** A link may be handed to the user's browser only if it is plain https (never file:, javascript:, custom schemes, http). */
export function externalTarget(url: string): string | null {
  try {
    const u = new URL(url);
    return u.protocol === 'https:' ? u.toString() : null;
  } catch {
    return null;
  }
}
