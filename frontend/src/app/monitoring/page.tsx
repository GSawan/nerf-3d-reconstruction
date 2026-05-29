'use client';
import { useRouter } from 'next/navigation';



export default function MonitoringPage() {
  const router = useRouter();

  const cards = [
    {
      id: 'grafana',
      title: 'Grafana',
      subtitle: 'Live Dashboards',
      description: 'Real-time charts for API throughput, P95 latency, reconstruction jobs, and error rates.',
      icon: '📊',
      href: '/grafana',
      color: 'orange',
      badge: 'LIVE',
    },
    {
      id: 'prometheus',
      title: 'Prometheus',
      subtitle: 'Metrics & Alerts',
      description: 'Raw metrics explorer. Query neo3d_reconstructions_total, http_request_duration_seconds, and more.',
      icon: '🔥',
      href: '/prometheus',
      color: 'red',
      badge: 'SCRAPING 15s',
    },
    {
      id: 'health',
      title: 'Health Check',
      subtitle: 'API Status',
      description: 'Backend health endpoint showing database connectivity and COLMAP availability.',
      icon: '✅',
      href: '/api/v1/health/',
      color: 'green',
      badge: 'JSON',
    },
    {
      id: 'metrics',
      title: 'Raw Metrics',
      subtitle: 'Prometheus Exposition',
      description: 'Raw OpenMetrics endpoint scraped by Prometheus. Shows all counters and gauges in text format.',
      icon: '📈',
      href: '/metrics',
      color: 'blue',
      badge: 'TEXT',
    },
  ];

  const colorMap: Record<string, string> = {
    orange: 'border-orange-500/30 hover:border-orange-500/60 text-orange-400',
    red: 'border-red-500/30 hover:border-red-500/60 text-red-400',
    green: 'border-emerald-500/30 hover:border-emerald-500/60 text-emerald-400',
    blue: 'border-blue-500/30 hover:border-blue-500/60 text-blue-400',
  };

  return (
    <div className="min-h-screen bg-[#080808] text-white" style={{ fontFamily: 'monospace' }}>
      {/* Background grid */}
      <div className="fixed inset-0 opacity-[0.02] pointer-events-none"
        style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,0.5) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.5) 1px,transparent 1px)', backgroundSize: '40px 40px' }} />

      {/* Header */}
      <header className="border-b border-white/10 bg-[#0d0d0d] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="w-6 h-6 border border-white/20 rotate-45 flex items-center justify-center">
            <div className="w-2 h-2 bg-white/80 rotate-45" />
          </div>
          <span className="text-sm font-bold tracking-[0.3em] uppercase">Neo3D</span>
          <span className="text-white/20 text-xs">/ Monitoring</span>
        </div>
        <button
          onClick={() => router.push('/')}
          className="text-xs border border-white/15 px-3 py-1.5 text-white/40 hover:text-white hover:border-white/40 transition-all"
        >
          ← Back
        </button>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10">
        <div className="mb-10">
          <h1 className="text-2xl font-bold tracking-widest uppercase mb-1">Monitoring</h1>
          <p className="text-white/25 text-xs tracking-wider">
            Production observability stack — Prometheus + Grafana running on the same EC2 instance.
          </p>
        </div>

        {/* Status bar */}
        <div className="border border-white/10 bg-[#0d0d0d] px-5 py-3 mb-8 flex items-center gap-6 text-[10px]">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-white/40 tracking-wider">PROMETHEUS SCRAPING</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-orange-400 animate-pulse" />
            <span className="text-white/40 tracking-wider">GRAFANA LIVE</span>
          </div>
          <div className="ml-auto text-white/20 tracking-wider">
            15s scrape interval · 15d retention
          </div>
        </div>

        {/* Cards */}
        <div className="grid grid-cols-2 gap-4 mb-10">
          {cards.map((card) => (
            <a
              key={card.id}
              href={card.href}
              target="_blank"
              rel="noopener noreferrer"
              className={`block border bg-[#0d0d0d] p-6 transition-all cursor-pointer group ${colorMap[card.color]}`}
            >
              <div className="flex items-start justify-between mb-3">
                <span className="text-2xl">{card.icon}</span>
                <span className={`text-[9px] tracking-widest px-2 py-0.5 border ${colorMap[card.color]}`}>
                  {card.badge}
                </span>
              </div>
              <h2 className="text-sm font-bold tracking-widest uppercase mb-0.5">{card.title}</h2>
              <p className="text-[10px] text-white/30 tracking-wider mb-3">{card.subtitle}</p>
              <p className="text-xs text-white/40 leading-relaxed">{card.description}</p>
              <div className="mt-4 text-[10px] tracking-widest text-white/20 group-hover:text-white/50 transition-colors">
                OPEN → {card.href}
              </div>
            </a>
          ))}
        </div>

        {/* Useful Prometheus queries */}
        <div className="border border-white/10 bg-[#0d0d0d] p-6">
          <h3 className="text-xs text-white/40 tracking-widest uppercase mb-4">Useful PromQL Queries</h3>
          <div className="space-y-3">
            {[
              { label: 'Request rate (req/s)', query: 'rate(http_requests_total[1m])' },
              { label: 'P95 Latency', query: 'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))' },
              { label: 'Total uploads', query: 'http_requests_total{handler="/api/v1/upload/",method="POST",status_code="200"}' },
              { label: 'Completed reconstructions', query: 'neo3d_reconstructions_total{status="completed"}' },
              { label: 'Active jobs', query: 'neo3d_active_jobs' },
            ].map(({ label, query }) => (
              <div key={label} className="flex items-start gap-4">
                <span className="text-[10px] text-white/30 tracking-wider w-40 shrink-0">{label}</span>
                <code className="text-[10px] text-blue-400/80 bg-blue-950/20 px-2 py-0.5 font-mono break-all">{query}</code>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
