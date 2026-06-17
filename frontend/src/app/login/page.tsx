'use client';

import { useState, useRef, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { Mail, KeyRound, AlertCircle, Loader2, ArrowRight } from 'lucide-react';
import { BASE_PATH } from '@/lib/base-path';

type Step = 'email' | 'code';

export default function LoginPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>('email');
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const codeInputRef = useRef<HTMLInputElement>(null);

  const requestCode = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setLoading(true);
    try {
      const res = await fetch(`${BASE_PATH}/api/auth/request-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Could not send the code.');

      setInfo(data.message || 'Check your email for a 6-digit code.');
      setStep('code');
      setTimeout(() => codeInputRef.current?.focus(), 50);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  };

  const verifyCode = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${BASE_PATH}/api/auth/verify-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), code: code.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'That code is incorrect or has expired.');

      router.push('/');
      router.refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-100 to-slate-200 flex items-center justify-center p-4 sm:p-6">
      <div className="max-w-sm w-full bg-white rounded-2xl shadow-xl overflow-hidden border border-slate-200">
        <div className="px-8 py-9 text-center bg-white border-b border-slate-100">
          <div className="text-3xl font-extrabold tracking-tight leading-none">
            <span className="text-brand-blue">erp</span>
            <span className="text-brand-sky">SOFT</span>
            <span className="text-brand-blue">app</span>
          </div>
          <p className="mt-2 text-sm text-slate-500">
            Sign in with your <strong className="text-slate-700">@erpsoftapp.com</strong> email
          </p>
        </div>

        <div className="p-8">
          {step === 'email' && (
            <form onSubmit={requestCode} className="space-y-4">
              <label className="block">
                <span className="text-sm font-medium text-slate-700">Work email</span>
                <div className="mt-1.5 relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <input
                    type="email"
                    required
                    autoFocus
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@erpsoftapp.com"
                    className="w-full pl-10 pr-3 py-2.5 rounded-lg border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-brand-blue/40 focus:border-brand-blue"
                  />
                </div>
              </label>

              {error && <ErrorBanner message={error} />}

              <button
                type="submit"
                disabled={loading || !email.trim()}
                className={`w-full py-3 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all shadow-md ${
                  loading || !email.trim()
                    ? 'bg-slate-200 text-slate-400 cursor-not-allowed shadow-none'
                    : 'bg-gradient-to-r from-brand-blue to-brand-sky text-white hover:brightness-105 hover:shadow-lg'
                }`}
              >
                {loading ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <>
                    Send me a code <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </form>
          )}

          {step === 'code' && (
            <form onSubmit={verifyCode} className="space-y-4">
              {info && (
                <p className="text-sm text-slate-600">
                  {info} Sent to <strong>{email}</strong>.
                </p>
              )}
              <label className="block">
                <span className="text-sm font-medium text-slate-700">6-digit code</span>
                <div className="mt-1.5 relative">
                  <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                  <input
                    ref={codeInputRef}
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    required
                    autoFocus
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/[^0-9]/g, ''))}
                    placeholder="123456"
                    className="w-full pl-10 pr-3 py-2.5 rounded-lg border border-slate-300 text-sm tracking-[0.3em] font-semibold focus:outline-none focus:ring-2 focus:ring-brand-blue/40 focus:border-brand-blue"
                  />
                </div>
              </label>

              {error && <ErrorBanner message={error} />}

              <button
                type="submit"
                disabled={loading || code.trim().length !== 6}
                className={`w-full py-3 rounded-xl font-semibold flex items-center justify-center gap-2 transition-all shadow-md ${
                  loading || code.trim().length !== 6
                    ? 'bg-slate-200 text-slate-400 cursor-not-allowed shadow-none'
                    : 'bg-gradient-to-r from-brand-blue to-brand-sky text-white hover:brightness-105 hover:shadow-lg'
                }`}
              >
                {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Verify & sign in'}
              </button>

              <button
                type="button"
                onClick={() => {
                  setStep('email');
                  setCode('');
                  setError(null);
                  setInfo(null);
                }}
                className="w-full text-center text-xs text-slate-400 hover:text-slate-600"
              >
                Use a different email
              </button>
            </form>
          )}
        </div>
      </div>
    </main>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="p-3 bg-red-50 text-red-700 rounded-lg flex items-start text-sm">
      <AlertCircle className="w-5 h-5 mr-2 flex-shrink-0" />
      <span>{message}</span>
    </div>
  );
}
