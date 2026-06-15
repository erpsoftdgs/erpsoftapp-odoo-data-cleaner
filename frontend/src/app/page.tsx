'use client';

import { useState, useRef } from 'react';
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
} from 'lucide-react';

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

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const detected = file ? detectType(file.name) : null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
      setError(null);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setFile(e.dataTransfer.files[0]);
      setError(null);
    }
  };

  const processFile = async () => {
    if (!file) {
      setError('Please select a file first.');
      return;
    }
    if (!detected) {
      setError('Rename the file to include "vendor" or "customer" so the cleaner knows what kind of data it is.');
      return;
    }

    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('data_type', detected.key);

    try {
      const response = await fetch('/api/clean', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to process file');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `cleaned_${file.name}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-100 to-slate-200 flex items-center justify-center p-4 sm:p-6">
      <div className="max-w-2xl w-full bg-white rounded-2xl shadow-xl overflow-hidden border border-slate-200">
        {/* Header — erpSOFTapp brand lockup */}
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
                'Name your file so it contains "vendor" or "customer" — this tells the cleaner what kind of data it is.',
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
                    className={`rounded-xl border p-4 text-center transition-colors ${
                      active
                        ? 'border-brand-blue bg-brand-blue/5'
                        : 'border-slate-200 bg-slate-50'
                    }`}
                  >
                    <Icon
                      className={`w-7 h-7 mx-auto mb-2 ${
                        active ? 'text-brand-blue' : 'text-slate-400'
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
            className={`block border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${
              file
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
                  Excel or OpenDocument — .xlsx, .xls, .ods
                </span>
              </div>
            )}
          </label>

          {/* Live filename detection feedback */}
          {file && detected && (
            <div className="mt-4 p-3 bg-green-50 text-green-800 rounded-lg flex items-center text-sm">
              <CheckCircle2 className="w-5 h-5 mr-2 flex-shrink-0" />
              <span>
                Detected as <strong>{detected.label}</strong> data — good to go.
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

          {/* Error */}
          {error && (
            <div className="mt-4 p-4 bg-red-50 text-red-700 rounded-lg flex items-start text-sm">
              <AlertCircle className="w-5 h-5 mr-3 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Action */}
          <button
            onClick={processFile}
            disabled={!file || !detected || loading}
            className={`mt-6 w-full py-4 text-lg font-semibold rounded-xl transition-all shadow-md flex justify-center items-center ${
              !file || !detected || loading
                ? 'bg-slate-200 text-slate-400 cursor-not-allowed shadow-none'
                : 'bg-gradient-to-r from-brand-blue to-brand-sky text-white hover:brightness-105 hover:shadow-lg hover:-translate-y-0.5'
            }`}
          >
            {loading ? (
              <>
                <Loader2 className="w-6 h-6 mr-3 animate-spin" />
                Cleaning with AI — this can take a minute…
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
              The AI cleans column names, splits addresses, and classifies records — your
              source columns don&apos;t need to be perfect.
            </p>
            <p className="flex items-center text-xs text-slate-500">
              <ShieldCheck className="w-4 h-4 mr-2 text-brand-green flex-shrink-0" />
              Files are processed on the server and removed right after the cleaned copy is
              generated.
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
