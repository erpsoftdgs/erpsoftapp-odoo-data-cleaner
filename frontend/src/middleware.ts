import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = "session";
const PUBLIC_PATHS = new Set(["/login"]);
const PUBLIC_API_PREFIXES = ["/api/auth/"];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const isPublicPath =
    PUBLIC_PATHS.has(pathname) || PUBLIC_API_PREFIXES.some((p) => pathname.startsWith(p));

  if (isPublicPath) return NextResponse.next();

  const hasSession = Boolean(request.cookies.get(SESSION_COOKIE)?.value);
  if (!hasSession) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = "/login";
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
