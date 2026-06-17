'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { LogOut, ShieldCheck, History, Loader2 } from 'lucide-react';
import { BASE_PATH } from '@/lib/base-path';

export default function TopBar({ email, isAdmin }: { email: string; isAdmin: boolean }) {
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);

  const signOut = async () => {
    setSigningOut(true);
    try {
      await fetch(`${BASE_PATH}/api/auth/logout`, { method: 'POST' });
      router.push('/login');
      router.refresh();
    } finally {
      setSigningOut(false);
    }
  };

  return (
    <header className="bg-white border-b border-slate-200 px-4 sm:px-6 py-2.5 flex items-center justify-between text-sm">
      <div className="flex items-center gap-4">
        <Link href="/" className="font-bold text-slate-700 hover:text-brand-blue">
          <span className="text-brand-blue">erp</span>
          <span className="text-brand-sky">SOFT</span>
          <span className="text-brand-blue">app</span>
        </Link>
        <Link
          href="/history"
          className="flex items-center gap-1.5 text-slate-500 hover:text-brand-blue transition-colors"
        >
          <History className="w-4 h-4" />
          History
        </Link>
        {isAdmin && (
          <Link
            href="/admin"
            className="flex items-center gap-1.5 text-slate-500 hover:text-brand-blue transition-colors"
          >
            <ShieldCheck className="w-4 h-4" />
            Admin report
          </Link>
        )}
      </div>
      <div className="flex items-center gap-3">
        <span className="text-slate-500 hidden sm:inline">{email}</span>
        <button
          onClick={signOut}
          disabled={signingOut}
          className="flex items-center gap-1.5 text-slate-500 hover:text-brand-red transition-colors disabled:opacity-50"
        >
          {signingOut ? <Loader2 className="w-4 h-4 animate-spin" /> : <LogOut className="w-4 h-4" />}
          Sign out
        </button>
      </div>
    </header>
  );
}
