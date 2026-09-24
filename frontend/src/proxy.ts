import { NextResponse, type NextRequest } from "next/server";
import {
  SESSION_COOKIE,
  sessionCookieOptions,
  signSessionToken,
  verifySessionToken,
} from "@/lib/auth";

const PUBLIC_PATHS = new Set(["/login", "/icon"]);
const PUBLIC_API_PREFIXES = ["/api/auth/"];

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isPublicPath =
    PUBLIC_PATHS.has(pathname) || PUBLIC_API_PREFIXES.some((prefix) => pathname.startsWith(prefix));

  if (isPublicPath) return NextResponse.next();

  const token = request.cookies.get(SESSION_COOKIE)?.value;
  const session = token ? await verifySessionToken(token) : null;
  if (!session) {
    if (pathname.includes("/api/")) {
      return NextResponse.json(
        { error: "Your session has expired. Please sign in again." },
        { status: 401 },
      );
    }

    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = "/login";
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // Keep the one-hour session alive while the user is actively using the app.
  const response = NextResponse.next();
  response.cookies.set(
    SESSION_COOKIE,
    await signSessionToken(session.email),
    sessionCookieOptions(),
  );
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
