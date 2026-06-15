import { NextResponse } from "next/server";
import { isAllowedEmail, ALLOWED_EMAIL_DOMAIN } from "@/lib/auth";
import { issueCode } from "@/lib/otp";
import { sendOtpEmail } from "@/lib/mailer";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let email: unknown;
  try {
    ({ email } = await request.json());
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  if (typeof email !== "string" || !email.includes("@")) {
    return NextResponse.json({ error: "Enter a valid email address." }, { status: 400 });
  }

  const normalised = email.trim().toLowerCase();

  if (!isAllowedEmail(normalised)) {
    return NextResponse.json(
      { error: `Only @${ALLOWED_EMAIL_DOMAIN} email addresses can sign in.` },
      { status: 403 }
    );
  }

  const result = issueCode(normalised);
  if (!result.ok) {
    return NextResponse.json(
      {
        error: `A code was already sent — wait ${Math.ceil(result.retryAfterMs / 1000)}s before requesting another.`,
      },
      { status: 429 }
    );
  }

  try {
    await sendOtpEmail(normalised, result.code);
  } catch (err) {
    console.error("Failed to send OTP email:", err);
    return NextResponse.json(
      { error: "Could not send the login email. Try again in a moment." },
      { status: 502 }
    );
  }

  return NextResponse.json({ message: "Check your email for a 6-digit code." });
}
