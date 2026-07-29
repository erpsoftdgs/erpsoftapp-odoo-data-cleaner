import { redirect } from 'next/navigation';
import { ClipboardList, Download, ChevronDown, Star, MessageSquare } from 'lucide-react';
import db from '@/lib/db';
import { formatDate, formatDuration, statusStyles, breakdownPhrase } from '@/lib/conversion-format';
import { getSession, isAdminEmail } from '@/lib/auth';
import { BASE_PATH } from '@/lib/base-path';

export const dynamic = 'force-dynamic';

type ConversionRow = {
  id: number;
  user_email: string;
  data_type: string;
  filename: string;
  rows_uploaded: number;
  rows_cleaned: number;
  rows_errors: number;
  rows_missing_fields: number;
  rows_duplicates: number;
  rows_internal: number;
  rows_is_company_flag: number;
  conversion_ms: number;
  status: string;
  created_at: number;
  downloaded_at: number;
  output_filename: string | null;
};

type RatingRow = {
  id: number;
  conversion_id: number | null;
  user_email: string;
  rating: number;
  feedback: string | null;
  created_at: number;
};

export default async function AdminPage() {
  const session = await getSession();
  if (!session || !isAdminEmail(session.email)) redirect('/');

  const rows = db
    .prepare('SELECT * FROM conversions ORDER BY created_at DESC')
    .all() as unknown as ConversionRow[];

  const ratings = db
    .prepare('SELECT * FROM ratings ORDER BY created_at DESC')
    .all() as unknown as RatingRow[];

  return (
    <main className="flex-1 bg-slate-50 p-4 sm:p-8 space-y-8">
      <div className="max-w-7xl mx-auto space-y-8">
        <div>
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
                      <th className="px-3 py-3 font-semibold">User</th>
                      <th className="px-3 py-3 font-semibold">Date</th>
                      <th className="px-3 py-3 font-semibold">File</th>
                      <th className="px-3 py-3 font-semibold text-right">Uploaded</th>
                      <th className="px-3 py-3 font-semibold text-right">Cleaned</th>
                      <th className="px-3 py-3 font-semibold">Time</th>
                      <th className="px-3 py-3 font-semibold">Downloaded</th>
                      <th className="px-3 py-3 font-semibold">Status</th>
                      <th className="px-3 py-3 font-semibold">Download</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/60">
                        <td className="px-3 py-3 text-slate-700">{row.user_email}</td>
                        <td className="px-3 py-3 text-slate-500 whitespace-nowrap">{formatDate(row.created_at)}</td>
                        <td className="px-3 py-3 text-slate-500">
                          <span className="block max-w-[16rem] truncate" title={row.filename}>
                            {row.filename}
                          </span>
                          <span className="text-xs text-slate-400 capitalize">{row.data_type}</span>
                        </td>
                        <td className="px-3 py-3 text-right text-slate-700 tabular-nums">{row.rows_uploaded}</td>
                        <td className="px-3 py-3 text-right text-slate-700 tabular-nums">{row.rows_cleaned}</td>
                        <td className="px-3 py-3 text-slate-500 whitespace-nowrap">{formatDuration(row.conversion_ms)}</td>
                        <td className="px-3 py-3 text-slate-500 whitespace-nowrap">{formatDate(row.downloaded_at)}</td>
                        <td className="px-3 py-3">
                          {(() => {
                            const phrase = breakdownPhrase({
                              missingFields: row.rows_missing_fields,
                              duplicates: row.rows_duplicates,
                              internal: row.rows_internal,
                              isCompanyFlag: row.rows_is_company_flag,
                            });
                            const badge = (
                              <span
                                className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium capitalize ${
                                  statusStyles[row.status] ?? 'bg-slate-100 text-slate-600'
                                }`}
                              >
                                {row.status}
                              </span>
                            );
                            if (!phrase) return badge;
                            return (
                              <details className="group">
                                <summary className="inline-flex items-center gap-1 cursor-pointer list-none [&::-webkit-details-marker]:hidden">
                                  {badge}
                                  <ChevronDown className="w-3 h-3 text-slate-400 group-open:rotate-180 transition-transform" />
                                </summary>
                                <p className="mt-1.5 text-xs text-slate-500 max-w-[14rem]">{phrase}</p>
                              </details>
                            );
                          })()}
                        </td>
                        <td className="px-3 py-3 whitespace-nowrap">
                          {row.output_filename ? (
                            <a
                              href={`${BASE_PATH}/api/conversions/${row.id}/download`}
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

        {/* User Ratings & Feedback Section */}
        <div>
          <div className="flex items-center gap-3 mb-6">
            <Star className="w-6 h-6 text-amber-500 fill-amber-400" />
            <div>
              <h2 className="text-xl font-bold text-slate-800">User ratings &amp; feedback</h2>
              <p className="text-sm text-slate-500">
                Post-cleaning session ratings and feedback submitted by users.
              </p>
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
            {ratings.length === 0 ? (
              <p className="p-8 text-center text-sm text-slate-500">
                No user ratings have been submitted yet.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                      <th className="px-4 py-3 font-semibold">User</th>
                      <th className="px-4 py-3 font-semibold">Date</th>
                      <th className="px-4 py-3 font-semibold">Rating</th>
                      <th className="px-4 py-3 font-semibold">Feedback / Comment</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ratings.map((r) => (
                      <tr key={r.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/60">
                        <td className="px-4 py-3 text-slate-700 font-medium">{r.user_email}</td>
                        <td className="px-4 py-3 text-slate-500 whitespace-nowrap">{formatDate(r.created_at)}</td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <div className="flex items-center gap-1">
                            {[1, 2, 3, 4, 5].map((star) => (
                              <Star
                                key={star}
                                className={`w-4 h-4 ${
                                  star <= r.rating ? 'text-amber-400 fill-amber-400' : 'text-slate-200'
                                }`}
                              />
                            ))}
                            <span className="ml-1 text-xs font-semibold text-slate-600">{r.rating}/5</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-slate-600">
                          {r.feedback ? (
                            <span className="italic text-slate-700">&ldquo;{r.feedback}&rdquo;</span>
                          ) : (
                            <span className="text-slate-400 text-xs font-light">No comment provided</span>
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
      </div>
    </main>
  );
}
