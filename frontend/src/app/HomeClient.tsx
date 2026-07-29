'use client';

import { useState, useRef } from 'react';
import Link from 'next/link';
import {
  UploadCloud,
  FileSpreadsheet,
  AlertCircle,
  Loader2,
  Users,
  Truck,
  CheckCircle2,
  Download,
  ShieldCheck,
  Sparkles,
  WifiOff,
  History,
  Star,
  X,
  LifeBuoy,
  Send,
} from 'lucide-react';
import { BASE_PATH } from '@/lib/base-path';
import { breakdownPhrase } from '@/lib/conversion-format';

// Mirrors the engine's SCHEMA_MAP (engine/odoo_data_engine.py) — the engine
// only knows how to clean these record types, so this must stay in sync.
// The detected key is sent to the backend as the `data_type` form field.
const DATA_TYPES = [
  { key: 'vendor', label: 'Vendors', icon: Truck, hint: 'e.g. vendor_blablabla.xlsx' },
  { key: 'customer', label: 'Customers', icon: Users, hint: 'e.g. customers_2024.xlsx' },
] as const;

function detectType(filename: string) {
  const name = filename.toLowerCase();
  return DATA_TYPES.find((t) => name.includes(t.key)) ?? null;
}

type ConversionResult = {
  id?: number;
  status: string;
  total: number;
  clean: number;
  errors: number;
  missingFields: number;
  duplicates: number;
  internal: number;
  isCompanyFlag: number;
};

export default function HomeClient() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isNetworkError, setIsNetworkError] = useState(false);
  const [result, setResult] = useState<ConversionResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Rate Me Popup state
  const [showRatingModal, setShowRatingModal] = useState(false);
  const [rating, setRating] = useState(0);
  const [hoverRating, setHoverRating] = useState(0);
  const [ratingFeedback, setRatingFeedback] = useState('');
  const [ratingSubmitted, setRatingSubmitted] = useState(false);
  const [submittingRating, setSubmittingRating] = useState(false);

  // Floating Support Modal state
  const [showSupportModal, setShowSupportModal] = useState(false);
  const [supportSubject, setSupportSubject] = useState('');
  const [supportMessage, setSupportMessage] = useState('');

  const detected = file ? detectType(file.name) : null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
      setError(null);
      setIsNetworkError(false);
      setResult(null);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setFile(e.dataTransfer.files[0]);
      setError(null);
      setIsNetworkError(false);
      setResult(null);
    }
  };

  const processFile = async () => {
    if (!file) {
      setError('Please select a file first.');
      setIsNetworkError(false);
      return;
    }
    if (!detected) {
      setError('Rename the file to include "vendor" or "customer" so the cleaner knows what kind of data it is.');
      setIsNetworkError(false);
      return;
    }

    setLoading(true);
    setError(null);
    setIsNetworkError(false);
    setResult(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('data_type', detected.key);

    try {
      const response = await fetch(`${BASE_PATH}/api/clean`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to process file');
      }

      // Stats ride along as headers since the response body is the raw
      // file, not JSON, read them before consuming the body as a blob.
      const convId = Number(response.headers.get('X-Conversion-ID')) || undefined;
      setResult({
        id: convId,
        status: response.headers.get('X-Conversion-Status') || 'success',
        total: Number(response.headers.get('X-Rows-Total')) || 0,
        clean: Number(response.headers.get('X-Rows-Clean')) || 0,
        errors: Number(response.headers.get('X-Rows-Errors')) || 0,
        missingFields: Number(response.headers.get('X-Rows-Missing-Fields')) || 0,
        duplicates: Number(response.headers.get('X-Rows-Duplicates')) || 0,
        internal: Number(response.headers.get('X-Rows-Internal')) || 0,
        isCompanyFlag: Number(response.headers.get('X-Rows-Is-Company-Flag')) || 0,
      });

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `cleaned_${file.name}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      // Trigger Rate Me popup short delay after download completes
      setTimeout(() => {
        setShowRatingModal(true);
      }, 700);
    } catch (err: unknown) {
      const isOffline = typeof navigator !== 'undefined' && !navigator.onLine;
      const errMsg = err instanceof Error ? err.message : 'An unexpected error occurred.';
      const isFetchError =
        isOffline ||
        err instanceof TypeError ||
        errMsg.includes('Failed to fetch') ||
        errMsg.includes('NetworkError') ||
        errMsg.toLowerCase().includes('network');

      if (isFetchError) {
        setIsNetworkError(true);
        setError(
          'Your connection was interrupted during processing. Don’t worry your file was uploaded and is cleaning on the server in the background.'
        );
      } else {
        setIsNetworkError(false);
        setError(errMsg);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-100 to-slate-200 flex items-center justify-center p-4 sm:p-6">
      <div className="max-w-2xl w-full bg-white rounded-2xl shadow-xl overflow-hidden border border-slate-200">
        {/* Header erpSOFTapp brand lockup */}
        <div className="px-8 py-9 text-center bg-white border-b border-slate-100">
          <div className="inline-block">
            <div className="text-4xl font-extrabold tracking-tight leading-none">
              <span className="text-brand-blue">erp</span>
              <span className="text-brand-sky">SOFT</span>
              <span className="text-brand-blue">app</span>
            </div>
            {/* green swoosh, echoing the logo */}
            <svg
              viewBox="0 0 240 16"
              className="mt-1 h-3 w-full"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <path
                d="M2 12 C 80 2, 170 2, 238 7"
                fill="none"
                stroke="var(--color-brand-green)"
                strokeWidth="3"
                strokeLinecap="round"
              />
            </svg>
            <p className="mt-1 text-xs font-medium text-brand-red">
              move your business to the next level
            </p>
          </div>

          <div className="mt-6 flex items-center justify-center gap-2">
            <FileSpreadsheet className="w-6 h-6 text-brand-blue" />
            <h1 className="text-2xl font-bold text-slate-800">Data Cleaner</h1>
          </div>
          <p className="mt-2 text-slate-500 max-w-md mx-auto text-sm">
            Turn messy spreadsheets into clean, ready to import files for Odoo powered by AI.
          </p>
        </div>

        <div className="p-8">
          {/* How it works */}
          <section className="mb-8">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-4">
              How it works
            </h2>
            <ol className="space-y-3">
              {[
                'Name your file so it contains "vendor" or "customer" this tells the cleaner what kind of data it is.',
                'Upload the spreadsheet below (.xlsx, .xls, or .ods). Columns can be messy or in any order.',
                'Click "Clean & Download". The AI maps, normalises, and formats your data, then a cleaned .xlsx downloads automatically.',
              ].map((step, i) => (
                <li key={i} className="flex items-start gap-3">
                  <span className="flex-shrink-0 w-6 h-6 rounded-full bg-brand-blue/10 text-brand-blue text-sm font-bold flex items-center justify-center">
                    {i + 1}
                  </span>
                  <span className="text-sm text-slate-700 leading-relaxed">{step}</span>
                </li>
              ))}
            </ol>
          </section>

          {/* Supported data types */}
          <section className="mb-8">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 mb-4">
              Supported data types
            </h2>
            <div className="grid grid-cols-2 gap-3">
              {DATA_TYPES.map((t) => {
                const Icon = t.icon;
                const active = detected?.key === t.key;
                return (
                  <div
                    key={t.key}
                    className={`rounded-xl border p-4 text-center transition-colors ${active
                      ? 'border-brand-blue bg-brand-blue/5'
                      : 'border-slate-200 bg-slate-50'
                      }`}
                  >
                    <Icon
                      className={`w-7 h-7 mx-auto mb-2 ${active ? 'text-brand-blue' : 'text-slate-400'
                        }`}
                    />
                    <div className="font-semibold text-slate-800 text-sm">{t.label}</div>
                    <div className="text-[11px] text-slate-400 mt-1">{t.hint}</div>
                  </div>
                );
              })}
            </div>
          </section>

          {/* Upload zone */}
          <label
            htmlFor="file-upload"
            className={`block border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${file
              ? 'border-brand-blue bg-brand-blue/5'
              : 'border-slate-300 hover:border-brand-sky hover:bg-slate-50'
              }`}
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
          >
            <input
              id="file-upload"
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              className="hidden"
              accept=".xlsx,.xls,.ods"
            />
            {file ? (
              <div className="flex flex-col items-center">
                <FileSpreadsheet className="w-12 h-12 text-brand-blue mb-3" />
                <span className="font-semibold text-slate-800">{file.name}</span>
                <span className="text-xs text-slate-500 mt-1">
                  {(file.size / 1024).toFixed(1)} KB
                </span>
              </div>
            ) : (
              <div className="flex flex-col items-center">
                <UploadCloud className="w-12 h-12 text-slate-400 mb-3" />
                <span className="font-medium text-slate-600 text-lg">
                  Click to upload or drag &amp; drop
                </span>
                <span className="text-sm text-slate-400 mt-2">
                  Excel or OpenDocument .xlsx, .xls, .ods
                </span>
              </div>
            )}
          </label>

          {/* Live filename detection feedback */}
          {file && detected && (
            <div className="mt-4 p-3 bg-green-50 text-green-800 rounded-lg flex items-center text-sm">
              <CheckCircle2 className="w-5 h-5 mr-2 flex-shrink-0" />
              <span>
                Detected as <strong>{detected.label}</strong> data is good to go.
              </span>
            </div>
          )}
          {file && !detected && (
            <div className="mt-4 p-3 bg-amber-50 text-amber-800 rounded-lg flex items-start text-sm">
              <AlertCircle className="w-5 h-5 mr-2 flex-shrink-0" />
              <span>
                The file name doesn&apos;t contain <strong>vendor</strong> or{' '}
                <strong>customer</strong>, so the cleaner can&apos;t tell what kind of data
                it is. Rename the file (e.g. <code>vendors_list.xlsx</code>) and upload
                again.
              </span>
            </div>
          )}

          {/* Error / Network Interruption Banner */}
          {error && isNetworkError && (
            <div className="mt-4 p-5 bg-amber-50 border border-amber-200 text-amber-900 rounded-xl flex items-start gap-3.5 text-sm shadow-sm">
              <WifiOff className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <div className="font-semibold text-amber-900 mb-1 text-sm">
                  Internet Connection Interrupted
                </div>
                <p className="text-amber-800 leading-relaxed text-xs sm:text-sm">
                  {error}
                </p>
                <div className="mt-3 flex items-center gap-3">
                  <Link
                    href="/history"
                    className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-amber-600 hover:bg-amber-700 text-white font-medium text-xs rounded-lg transition-colors shadow-sm"
                  >
                    <History className="w-3.5 h-3.5" />
                    Check History &amp; Download File
                  </Link>
                </div>
              </div>
            </div>
          )}

          {error && !isNetworkError && (
            <div className="mt-4 p-4 bg-red-50 text-red-700 rounded-lg flex items-start text-sm">
              <AlertCircle className="w-5 h-5 mr-3 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Conversion result, flags rows that need review instead of
              silently downloading a file that's missing them. */}
          {result && result.status === 'partial' && (
            <div className="mt-4 p-4 bg-amber-50 text-amber-800 rounded-lg flex items-start text-sm">
              <AlertCircle className="w-5 h-5 mr-3 flex-shrink-0" />
              <span>
                Downloaded but <strong>{result.errors}</strong> of {result.total} row
                {result.total === 1 ? '' : 's'} need review
                {breakdownPhrase(result) && <> ({breakdownPhrase(result)})</>}. They&apos;re
                still in the file, highlighted in red on the <strong>Data</strong> sheet, with
                the reason listed on the <strong>Errors</strong> sheet.
              </span>
            </div>
          )}
          {result && result.status === 'success' && (
            <div className="mt-4 p-4 bg-green-50 text-green-700 rounded-lg flex items-start text-sm">
              <CheckCircle2 className="w-5 h-5 mr-3 flex-shrink-0" />
              <span>
                Downloaded all <strong>{result.total}</strong> rows cleaned successfully.
              </span>
            </div>
          )}

          {/* Action */}
          <button
            onClick={processFile}
            disabled={!file || !detected || loading}
            className={`mt-6 w-full py-4 text-lg font-semibold rounded-xl transition-all shadow-md flex justify-center items-center ${!file || !detected || loading
              ? 'bg-slate-200 text-slate-400 cursor-not-allowed shadow-none'
              : 'bg-gradient-to-r from-brand-blue to-brand-sky text-white hover:brightness-105 hover:shadow-lg hover:-translate-y-0.5'
              }`}
          >
            {loading ? (
              <>
                <Loader2 className="w-6 h-6 mr-3 animate-spin" />
                Cleaning with AI, this can take a minute…
              </>
            ) : (
              <>
                <Download className="w-5 h-5 mr-2" />
                Clean &amp; Download
              </>
            )}
          </button>

          {/* Footer notes */}
          <div className="mt-6 pt-5 border-t border-slate-100 space-y-2">
            <p className="flex items-center text-xs text-slate-500">
              <Sparkles className="w-4 h-4 mr-2 text-brand-sky flex-shrink-0" />
              The AI cleans column names, splits addresses, and classifies records your
              source columns don&apos;t need to be perfect.
            </p>
            <p className="flex items-center text-xs text-slate-500">
              <ShieldCheck className="w-4 h-4 mr-2 text-brand-green flex-shrink-0" />
              If your Wi-Fi drops while processing, your file is saved on the server and reachable in{' '}
              <Link href="/history" className="text-brand-blue font-medium underline ml-1">
                History
              </Link>.
            </p>
          </div>
        </div>
      </div>

      {/* Floating Support Button */}
      <button
        onClick={() => setShowSupportModal(true)}
        className="fixed bottom-6 right-6 z-40 bg-brand-blue hover:bg-slate-800 text-white font-medium px-4 py-3 rounded-full shadow-xl flex items-center gap-2.5 transition-all animate-bounce hover:scale-105 active:scale-95 border border-white/20"
        title="Need help? Contact support"
      >
        <LifeBuoy className="w-5 h-5 text-brand-sky" />
        <span className="text-sm font-semibold">Support</span>
      </button>

      {/* Support Modal */}
      {showSupportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fadeIn">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200 relative">
            <button
              onClick={() => setShowSupportModal(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 transition-colors p-1"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-brand-blue/10 flex items-center justify-center text-brand-blue">
                <LifeBuoy className="w-5 h-5 text-brand-blue" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-slate-800">Contact Support</h3>
                <p className="text-xs text-slate-500">Send an email directly to our support team</p>
              </div>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                const subject = encodeURIComponent(supportSubject || 'Support Request - Data Cleaner');
                const body = encodeURIComponent(supportMessage);
                window.location.href = `mailto:eniola@erpsoftapp.com?cc=johnnoah620@gmail.com&subject=${subject}&body=${body}`;
                setShowSupportModal(false);
                setSupportSubject('');
                setSupportMessage('');
              }}
              className="space-y-4"
            >
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Subject</label>
                <input
                  type="text"
                  value={supportSubject}
                  onChange={(e) => setSupportSubject(e.target.value)}
                  placeholder="e.g. Need assistance with spreadsheet import"
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-blue/30 focus:border-brand-blue"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Message</label>
                <textarea
                  rows={4}
                  value={supportMessage}
                  onChange={(e) => setSupportMessage(e.target.value)}
                  placeholder="Describe your issue or question..."
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-blue/30 focus:border-brand-blue resize-none"
                  required
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowSupportModal(false)}
                  className="px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 text-xs font-semibold text-white bg-brand-blue hover:bg-brand-blue/90 rounded-lg shadow transition-all flex items-center gap-1.5"
                >
                  <Send className="w-3.5 h-3.5" />
                  Send Email
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Rate Me Modal */}
      {showRatingModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fadeIn">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200 relative text-center">
            <button
              onClick={() => {
                setShowRatingModal(false);
                setRatingSubmitted(false);
                setRating(0);
              }}
              className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 transition-colors p-1"
            >
              <X className="w-5 h-5" />
            </button>

            {ratingSubmitted ? (
              <div className="py-6">
                <div className="w-14 h-14 mx-auto rounded-full bg-green-100 text-green-600 flex items-center justify-center mb-3">
                  <CheckCircle2 className="w-8 h-8" />
                </div>
                <h3 className="text-xl font-bold text-slate-800">Thank You!</h3>
                <p className="text-xs text-slate-500 mt-1.5 max-w-xs mx-auto">
                  Your feedback helps us continuously improve the erpSOFTapp Data Cleaner.
                </p>
                <button
                  onClick={() => {
                    setShowRatingModal(false);
                    setRatingSubmitted(false);
                    setRating(0);
                  }}
                  className="mt-5 px-6 py-2 bg-brand-blue text-white text-xs font-semibold rounded-lg hover:bg-brand-blue/90 transition-colors shadow-sm"
                >
                  Done
                </button>
              </div>
            ) : (
              <div>
                <div className="w-12 h-12 mx-auto rounded-full bg-amber-100 text-amber-500 flex items-center justify-center mb-3">
                  <Star className="w-6 h-6 fill-amber-400" />
                </div>
                <h3 className="text-xl font-bold text-slate-800">How was your session?</h3>
                <p className="text-xs text-slate-500 mt-1">
                  Rate your data cleaning experience to help us improve.
                </p>

                {/* Star Rating Controls */}
                <div className="flex justify-center gap-2 my-5">
                  {[1, 2, 3, 4, 5].map((star) => (
                    <button
                      key={star}
                      type="button"
                      onMouseEnter={() => setHoverRating(star)}
                      onMouseLeave={() => setHoverRating(0)}
                      onClick={() => setRating(star)}
                      className="p-1 transition-transform hover:scale-125 focus:outline-none"
                    >
                      <Star
                        className={`w-8 h-8 transition-colors ${star <= (hoverRating || rating)
                          ? 'text-amber-400 fill-amber-400'
                          : 'text-slate-300'
                          }`}
                      />
                    </button>
                  ))}
                </div>

                {/* Optional Feedback Textarea */}
                <textarea
                  rows={3}
                  value={ratingFeedback}
                  onChange={(e) => setRatingFeedback(e.target.value)}
                  placeholder="Tell us what went well or how we can improve (optional)…"
                  className="w-full p-3 text-xs border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-amber-400/40 resize-none text-slate-700 mb-4"
                />

                <div className="flex items-center justify-end gap-2">
                  <button
                    onClick={() => {
                      setShowRatingModal(false);
                      setRating(0);
                    }}
                    className="px-4 py-2 text-xs font-medium text-slate-500 hover:bg-slate-100 rounded-lg transition-colors"
                  >
                    Skip
                  </button>
                  <button
                    disabled={rating === 0 || submittingRating || ratingSubmitted}
                    onClick={async () => {
                      if (submittingRating || ratingSubmitted) return;
                      setSubmittingRating(true);
                      try {
                        await fetch(`${BASE_PATH}/api/rating`, {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({
                            rating,
                            feedback: ratingFeedback,
                            conversionId: result?.id,
                          }),
                        });
                      } catch (err) {
                        console.error('Failed to submit rating:', err);
                      } finally {
                        setSubmittingRating(false);
                        setRatingSubmitted(true);
                      }
                    }}
                    className={`px-5 py-2 text-xs font-semibold text-white rounded-lg transition-all shadow-sm ${
                      rating === 0 || submittingRating || ratingSubmitted
                        ? 'bg-slate-200 cursor-not-allowed text-slate-400'
                        : 'bg-amber-500 hover:bg-amber-600'
                    }`}
                  >
                    {submittingRating ? 'Submitting…' : 'Submit Rating'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
