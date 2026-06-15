import { NextResponse } from "next/server";
import { isAllowedEmail, setSessionCookie } from "@/lib/auth";
import { consumeCode } from "@/lib/otp";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let body: { email?: unknown; code?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  const { email, code } = body;
  if (typeof email !== "string" || typeof code !== "string" || !code.trim()) {
    return NextResponse.json({ error: "Enter the 6-digit code from your email." }, { status: 400 });
  }

  const normalised = email.trim().toLowerCase();
  if (!isAllowedEmail(normalised)) {
    return NextResponse.json({ error: "That email address isn't allowed." }, { status: 403 });
  }

  if (!consumeCode(normalised, code)) {
    return NextResponse.json({ error: "That code is incorrect or has expired." }, { status: 401 });
  }

  await setSessionCookie(normalised);
  return NextResponse.json({ message: "Signed in." });
}
