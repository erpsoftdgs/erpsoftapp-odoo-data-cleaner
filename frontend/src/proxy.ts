import { NextResponse, type NextRequest } from "next/server";
import {
  verifySessionToken,
  signSessionToken,
  sessionCookieOptions,
  isAdminEmail,
  SESSION_COOKIE,
} from "@/lib/auth";

const PUBLIC_PATHS = new Set(["/login"]);
const PUBLIC_API_PREFIXES = ["/api/auth/"];

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const token = request.cookies.get(SESSION_COOKIE)?.value;
  const session = token ? await verifySessionToken(token) : null;

  const isPublicPath =
    PUBLIC_PATHS.has(pathname) || PUBLIC_API_PREFIXES.some((p) => pathname.startsWith(p));

  if (isPublicPath) {
    // Already signed in — no reason to show the login page again.
    if (pathname === "/login" && session) {
      return NextResponse.redirect(new URL("/", request.url));
    }
    return NextResponse.next();
  }

  if (!session) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", pathname);
    const response = NextResponse.redirect(loginUrl);
    if (token) response.cookies.delete(SESSION_COOKIE); // stale/expired — clear it
    return response;
  }

  if (pathname.startsWith("/admin") && !isAdminEmail(session.email)) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  // Sliding 1-hour inactivity window: re-sign the token on every authenticated
  // request so the expiry keeps moving forward while the user is active, and
  // only lapses after an hour of no requests.
  const response = NextResponse.next();
  const refreshed = await signSessionToken(session.email);
  response.cookies.set(SESSION_COOKIE, refreshed, sessionCookieOptions());
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
