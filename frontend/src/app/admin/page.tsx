import { redirect } from 'next/navigation';
import { ClipboardList, Download } from 'lucide-react';
import db from '@/lib/db';
import { formatDate, formatDuration, statusStyles } from '@/lib/conversion-format';
import { getSession, isAdminEmail } from '@/lib/auth';

export const dynamic = 'force-dynamic';

type ConversionRow = {
  id: number;
  user_email: string;
  data_type: string;
  filename: string;
  rows_uploaded: number;
  rows_cleaned: number;
  rows_errors: number;
  conversion_ms: number;
  status: string;
  created_at: number;
  downloaded_at: number;
  output_filename: string | null;
};

export default async function AdminPage() {
  const session = await getSession();
  if (!session || !isAdminEmail(session.email)) redirect('/');

  const rows = db
    .prepare('SELECT * FROM conversions ORDER BY created_at DESC')
    .all() as unknown as ConversionRow[];

  return (
    <main className="flex-1 bg-slate-50 p-4 sm:p-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <ClipboardList className="w-6 h-6 text-brand-blue" />
          <div>
            <h1 className="text-xl font-bold text-slate-800">Conversion history</h1>
            <p className="text-sm text-slate-500">
              Every file run through the data cleaner, across all users.
            </p>
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
          {rows.length === 0 ? (
            <p className="p-8 text-center text-sm text-slate-500">
              No conversions have been logged yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                    <th className="px-4 py-3 font-semibold">User</th>
                    <th className="px-4 py-3 font-semibold">Date</th>
                    <th className="px-4 py-3 font-semibold">File</th>
                    <th className="px-4 py-3 font-semibold text-right">Rows uploaded</th>
                    <th className="px-4 py-3 font-semibold text-right">Rows cleaned</th>
                    <th className="px-4 py-3 font-semibold">Conversion time</th>
                    <th className="px-4 py-3 font-semibold">Downloaded</th>
                    <th className="px-4 py-3 font-semibold">Status</th>
                    <th className="px-4 py-3 font-semibold">Download</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/60">
                      <td className="px-4 py-3 text-slate-700">{row.user_email}</td>
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap">{formatDate(row.created_at)}</td>
                      <td className="px-4 py-3 text-slate-500">
                        <span className="block max-w-[16rem] truncate" title={row.filename}>
                          {row.filename}
                        </span>
                        <span className="text-xs text-slate-400 capitalize">{row.data_type}</span>
                      </td>
                      <td className="px-4 py-3 text-right text-slate-700 tabular-nums">{row.rows_uploaded}</td>
                      <td className="px-4 py-3 text-right text-slate-700 tabular-nums">{row.rows_cleaned}</td>
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap">{formatDuration(row.conversion_ms)}</td>
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap">{formatDate(row.downloaded_at)}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium capitalize ${
                            statusStyles[row.status] ?? 'bg-slate-100 text-slate-600'
                          }`}
                        >
                          {row.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {row.output_filename ? (
                          <a
                            href={`/api/conversions/${row.id}/download`}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-brand-blue/10 text-brand-blue text-xs font-medium hover:bg-brand-blue/20 transition-colors"
                          >
                            <Download className="w-3.5 h-3.5" />
                            Download
                          </a>
                        ) : (
                          <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-400">
                            Expired
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
