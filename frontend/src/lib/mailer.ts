import nodemailer, { type Transporter } from "nodemailer";

let transporter: Transporter | null | undefined;

function getTransporter(): Transporter | null {
  if (transporter !== undefined) return transporter;

  const { SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS } = process.env;
  if (!SMTP_HOST || !SMTP_USER || !SMTP_PASS) {
    transporter = null;
    return transporter;
  }

  const port = Number(SMTP_PORT) || 587;
  transporter = nodemailer.createTransport({
    host: SMTP_HOST,
    port,
    secure: port === 465,
    auth: { user: SMTP_USER, pass: SMTP_PASS },
  });
  return transporter;
}

/**
 * Sends the OTP code by email. If SMTP isn't configured yet (no SMTP_HOST/
 * SMTP_USER/SMTP_PASS in .env), logs the code to the server console instead —
 * this keeps the login flow testable end-to-end before real credentials land.
 */
export async function sendOtpEmail(email: string, code: string): Promise<void> {
  const mailer = getTransporter();

  if (!mailer) {
    console.log(`\n🔑 [DEV] Login code for ${email}: ${code}\n   (SMTP not configured — set SMTP_HOST/SMTP_USER/SMTP_PASS in .env to send real emails)\n`);
    return;
  }

  const from = process.env.SMTP_FROM || "erpSOFTapp <services@erpsoftapp.com>";

  await mailer.sendMail({
    from,
    to: email,
    subject: "Your erpSOFTapp sign-in code",
    text: `Your sign-in code is ${code}.\n\nEnter it on the login page to continue. It expires in 10 minutes and can only be used once.\n\nIf you didn't request this, you can safely ignore this email.`,
    html: `
<!DOCTYPE html>
<html lang="en">
  <body style="margin:0; padding:0; background-color:#eef2f7; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#eef2f7; padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px; width:100%; background-color:#ffffff; border-radius:16px; overflow:hidden; box-shadow:0 4px 24px rgba(15,23,42,0.08);">
            <tr>
              <td style="background:linear-gradient(135deg,#0a6cb0,#29a9e0); padding:28px 32px; text-align:center;">
                <span style="font-size:22px; font-weight:800; letter-spacing:0.3px; color:#ffffff;">
                  erp<span style="color:#dff3ff;">SOFT</span>app
                </span>
              </td>
            </tr>
            <tr>
              <td style="padding:36px 32px 8px; text-align:center;">
                <p style="margin:0 0 8px; font-size:15px; color:#475569;">Here is your sign-in code for the Data Cleaner:</p>
                <p style="margin:20px 0; font-size:38px; font-weight:800; letter-spacing:10px; color:#075089; font-family:'SFMono-Regular',Consolas,Menlo,monospace;">
                  ${code}
                </p>
                <p style="margin:0; font-size:13px; color:#94a3b8;">This code expires in <strong style="color:#64748b;">10 minutes</strong> and can only be used once.</p>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 32px 32px;">
                <hr style="border:none; border-top:1px solid #e2e8f0; margin:0 0 20px;" />
                <p style="margin:0; font-size:12px; line-height:1.6; color:#94a3b8; text-align:center;">
                  Didn't request this code? You can safely ignore this email — your account is still secure.<br />
                  Sent to ${email} for sign-in to the erpSOFTapp Data Cleaner.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
    `,
  });
}
