'use client';

import { useEffect, useState } from 'react';

type AnalyticsStats = {
  total: number;
  successful: number;
  failed: number;
  active: number;
  success_rate: number;
};

const EMPTY_STATS: AnalyticsStats = {
  total: 0,
  successful: 0,
  failed: 0,
  active: 0,
  success_rate: 0,
};

export default function AnalyticsPage() {
  const [stats, setStats] = useState<AnalyticsStats>(EMPTY_STATS);

  useEffect(() => {
    let cancelled = false;

    const loadStats = async () => {
      try {
        const response = await fetch('/api/analytics', {
          cache: 'no-store',
        });

        if (!response.ok) {
          throw new Error(`Analytics request failed: ${response.status}`);
        }

        const data = (await response.json()) as Partial<AnalyticsStats>;

        if (!cancelled) {
          setStats({
            total: Number(data.total ?? 0),
            successful: Number(data.successful ?? 0),
            failed: Number(data.failed ?? 0),
            active: Number(data.active ?? 0),
            success_rate: Number(data.success_rate ?? 0),
          });
        }
      } catch (error) {
        console.error('Analytics dashboard fetch failed:', error);
      }
    };

    loadStats();
    const intervalId = setInterval(loadStats, 2000);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, []);

  return (
    <main className="min-h-screen bg-slate-950 p-10 text-white">
      <h1 className="text-4xl font-bold text-cyan-400">
        MediSathi
      </h1>

      <h2 className="mt-2 text-3xl font-bold">
        Call Analytics Dashboard
      </h2>

      <div className="mt-10 grid gap-6 md:grid-cols-3">
        <div className="rounded-2xl bg-slate-900 p-8">
          <p className="text-slate-400">Total Calls</p>
          <p className="mt-3 text-5xl font-bold">{stats.total}</p>
        </div>

        <div className="rounded-2xl bg-slate-900 p-8">
          <p className="text-slate-400">Successful Calls</p>
          <p className="mt-3 text-5xl font-bold text-green-400">
            {stats.successful}
          </p>
        </div>

        <div className="rounded-2xl bg-slate-900 p-8">
          <p className="text-slate-400">Failed Calls</p>
          <p className="mt-3 text-5xl font-bold text-red-400">
            {stats.failed}
          </p>
        </div>
      </div>

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <div className="rounded-2xl bg-slate-900 p-8">
          <p className="text-slate-400">Active Calls</p>
          <p className="mt-3 text-5xl font-bold text-cyan-400">
            {stats.active}
          </p>
        </div>

        <div className="rounded-2xl bg-slate-900 p-8">
          <p className="text-slate-400">Success Rate</p>
          <p className="mt-3 text-5xl font-bold text-amber-400">
            {stats.success_rate}%
          </p>
        </div>
      </div>

      <a
        href="/"
        className="mt-10 inline-block rounded-full bg-cyan-500 px-6 py-3 font-semibold text-black"
      >
        🎙️ Back to MediSathi
      </a>
    </main>
  );
}