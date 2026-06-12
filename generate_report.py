#!/usr/bin/env python3
"""Generate a web (HTML) + PDF report of XWiki metrics across versions from
GMT measurements.

Fetches runs and per-phase stats from a GMT API (the hosted cluster by
default), selects the latest successful run per (version, scenario), and
renders charts of the [RUNTIME] phase metrics with one series per scenario
across versions.

Usage:
  ./generate_report.py                       # report/index.html from hosted API
  ./generate_report.py --pdf                 # also render report/report.pdf
  ./generate_report.py --api-url http://api.green-coding.internal:9142 \
                       --uri /home/mleduc/gmt-xwiki   # local GMT instance

PDF rendering uses Playwright/Chromium: the local venv if importable,
otherwise the greencoding/gcb_playwright container (needs docker).
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RUN_NAME_RE = re.compile(r'^xwiki-(?P<version>[0-9.]+) (?P<scenario>\w+)$')

# metric key -> (label, detail selector, divisor, display unit)
# detail selector: explicit detail name, 'first' or 'sum' (over containers)
METRICS = [
    ('psu_energy_ac_mcp_machine',     'Machine energy',        'first', 1e6, 'J'),
    ('psu_power_ac_mcp_machine',      'Avg. machine power',    'first', 1e3, 'W'),
    ('cpu_energy_rapl_msr_component', 'CPU package energy',    'first', 1e6, 'J'),
    ('psu_carbon_ac_mcp_machine',     'Operational carbon',    'first', 1e3, 'mgCO2e'),
    ('phase_time_syscall_system',     'Runtime duration',      'first', 1e6, 's'),
    ('cpu_utilization_procfs_system', 'CPU utilization',       'first', 1e2, '%'),
    ('memory_used_cgroup_container',  'XWiki container memory', 'xwiki', 1e6, 'MB'),
    ('network_total_cgroup_container', 'Network traffic',      'sum',   1e6, 'MB'),
]
ATTRIBUTION_METRIC = 'psu_energy_cgroup_container'   # per-container energy share


def api_get(api_url, path):
    req = urllib.request.Request(f"{api_url}{path}", headers={'User-Agent': 'gmt-xwiki-report'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def version_key(version):
    return tuple(int(p) for p in version.split('.'))


def select_runs(api_url, uri, scenarios):
    """Latest successful run per (version, scenario)."""
    rows = api_get(api_url, f"/v2/runs?uri={urllib.parse.quote(uri)}&limit=0")['data']
    selected = {}
    for row in rows:
        run_id, name, _uri, _branch, created_at = row[0], row[1], row[2], row[3], row[4]
        machine, commit, end_measurement, failed = row[8], row[9], row[10], row[11]
        m = RUN_NAME_RE.match(name)
        if not m or failed or end_measurement is None:
            continue
        version, scenario = m.group('version'), m.group('scenario')
        if scenarios and scenario not in scenarios:
            continue
        key = (version, scenario)
        # rows come newest-first; keep the most recent successful run
        if key not in selected:
            selected[key] = {'id': run_id, 'created_at': created_at,
                             'machine': machine, 'commit': commit}
    return selected


def extract_value(phase_data, metric, detail):
    m = phase_data.get(metric)
    if not m:
        return None
    details = m['data']
    if detail == 'sum':
        names = details.keys()
    elif detail == 'first':
        names = list(details.keys())[:1]
    else:
        names = [detail] if detail in details else []
    total = 0
    for name in names:
        runs = details[name]['data']
        total += next(iter(runs.values()))['mean']
    return total if names else None


def collect(api_url, runs):
    """-> {(version, scenario): {'metrics': {label: value}, 'attribution': {container: J}, run meta}}"""
    out = {}
    for (version, scenario), meta in sorted(runs.items()):
        print(f"  fetching phase stats: xwiki-{version} {scenario} ({meta['id']})")
        stats = api_get(api_url, f"/v1/phase_stats/single/{meta['id']}")['data']['data']
        runtime = stats.get('[RUNTIME]', {}).get('data', {})
        values = {}
        for metric, label, detail, div, unit in METRICS:
            raw = extract_value(runtime, metric, detail)
            values[label] = None if raw is None else round(raw / div, 2)
        attribution = {}
        attr = runtime.get(ATTRIBUTION_METRIC, {}).get('data', {})
        for container, d in attr.items():
            attribution[container] = round(next(iter(d['data'].values()))['mean'] / 1e6, 2)
        out[(version, scenario)] = {**meta, 'metrics': values, 'attribution': attribution}
    return out


def build_html(data, api_url, uri):
    versions = sorted({v for v, _ in data}, key=version_key)
    scenarios = sorted({s for _, s in data})
    units = {label: unit for _, label, _, _, unit in METRICS}

    series_per_metric = {}
    for _, label, _, _, _ in METRICS:
        series_per_metric[label] = {
            s: [data.get((v, s), {}).get('metrics', {}).get(label) for v in versions]
            for s in scenarios
        }
    attribution = {
        s: {v: data.get((v, s), {}).get('attribution', {}) for v in versions}
        for s in scenarios
    }
    table = [
        {'version': v, 'scenario': s, 'id': d['id'], 'machine': d['machine'],
         'commit': (d['commit'] or '')[:8], 'created_at': d['created_at'][:16],
         **{label: val for label, val in d['metrics'].items()}}
        for (v, s), d in sorted(data.items(), key=lambda kv: (version_key(kv[0][0]), kv[0][1]))
    ]
    payload = json.dumps({'versions': versions, 'scenarios': scenarios,
                          'units': units, 'metrics': series_per_metric,
                          'attribution': attribution, 'table': table,
                          'dashboard': api_url.replace('api.', 'metrics.')})
    generated = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>XWiki across versions — GMT report</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"
        integrity="sha384-Mx5lkUEQPM1pOJCwFtUICyX45KNojXbkWdYhkKUKsbv391mavbfoAmONbzkgYPzR"
        crossorigin="anonymous"></script>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 1100px; color: #222; }}
  h1 {{ font-size: 1.6rem; }} h2 {{ font-size: 1.15rem; margin-top: 2.2rem; }}
  .meta {{ color: #666; font-size: .85rem; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2.2rem 1rem; }}
  .chart {{ width: 100%; height: 320px; }}
  table {{ border-collapse: collapse; font-size: .8rem; width: 100%; margin-top: 1rem; }}
  th, td {{ border: 1px solid #ddd; padding: .35rem .5rem; text-align: right; }}
  th {{ background: #f5f5f5; }} td:nth-child(-n+2), th:nth-child(-n+2) {{ text-align: left; }}
  a {{ color: #2a6db0; }}
  .footnote {{ font-size: .8rem; color: #666; margin-top: 1.5rem; }}
  @media print {{
    .grid {{ grid-template-columns: 1fr 1fr; }}
    .chart {{ height: 280px; }}
    h2 {{ break-before: auto; }} .chart, table {{ break-inside: avoid; }}
  }}
</style>
</head>
<body>
<h1>XWiki across versions — Green Metrics Tool report</h1>
<p class="meta">Repository: {uri} · Source: {api_url} · Generated: {generated}<br>
Latest successful run per version/scenario, metrics from the measured <code>[RUNTIME]</code> phase.</p>

<div id="scenario-sections"></div>

<h2>Runs included</h2>
<div id="table"></div>

<p class="footnote">Operational carbon uses the live grid intensity at the time of each
run (electricitymaps), so carbon values are not directly comparable across runs —
compare energy instead. Memory/CPU/network are means or totals over the runtime phase.</p>

<script>
const D = {payload};
const charts = [];
const sections = document.getElementById('scenario-sections');
const palette = ['#5470c6', '#91cc75', '#fac858', '#ee6666'];
D.scenarios.forEach((s, idx) => {{
  const h = document.createElement('h2');
  h.textContent = `Scenario: ${{s}} — evolution across versions`;
  sections.appendChild(h);
  const grid = document.createElement('div'); grid.className = 'grid';
  sections.appendChild(grid);
  for (const [label, seriesMap] of Object.entries(D.metrics)) {{
    const el = document.createElement('div'); el.className = 'chart'; grid.appendChild(el);
    const c = echarts.init(el);
    c.setOption({{
      title: {{ text: label + (D.units[label] ? ` (${{D.units[label]}})` : ''), textStyle: {{ fontSize: 13 }} }},
      tooltip: {{ trigger: 'axis' }},
      grid: {{ top: 45, left: 55, right: 10, bottom: 25 }},
      xAxis: {{ type: 'category', data: D.versions }},
      yAxis: {{ type: 'value' }},
      series: [{{ name: s, type: 'bar', data: seriesMap[s], itemStyle: {{ color: palette[idx % palette.length] }} }}],
      animation: false,
    }});
    charts.push(c);
  }}
  // per-container energy attribution for this scenario
  const el = document.createElement('div'); el.className = 'chart'; grid.appendChild(el);
  const containers = [...new Set(Object.values(D.attribution[s]).flatMap(o => Object.keys(o)))];
  const c = echarts.init(el);
  c.setOption({{
    title: {{ text: 'Energy attribution per container (J)', textStyle: {{ fontSize: 13 }} }},
    tooltip: {{ trigger: 'axis' }}, legend: {{ top: 22, textStyle: {{ fontSize: 11 }} }},
    grid: {{ top: 60, left: 55, right: 10, bottom: 25 }},
    xAxis: {{ type: 'category', data: D.versions }},
    yAxis: {{ type: 'value' }},
    series: containers.map(name => ({{ name, type: 'bar', stack: 'e',
      data: D.versions.map(v => (D.attribution[s][v] || {{}})[name] ?? null) }})),
    animation: false,
  }});
  charts.push(c);
}});
const cols = ['version', 'scenario', ...Object.keys(D.units), 'machine', 'commit', 'created_at'];
const head = '<tr>' + cols.map(c => `<th>${{c}}</th>`).join('') + '<th>run</th></tr>';
const rows = D.table.map(r => '<tr>' + cols.map(c => `<td>${{r[c] ?? ''}}</td>`).join('')
  + `<td><a href="${{D.dashboard}}/stats.html?id=${{r.id}}">stats</a></td></tr>`).join('');
document.getElementById('table').innerHTML = `<table>${{head}}${{rows}}</table>`;
window.addEventListener('resize', () => charts.forEach(c => c.resize()));
window.__charts_ready = true;   // polled by the PDF renderer
</script>
</body>
</html>
"""


PDF_SNIPPET = """
import sys
from playwright.sync_api import sync_playwright
html, pdf = sys.argv[1], sys.argv[2]
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={'width': 1100, 'height': 800})
    page.goto(f'file://{html}')
    page.wait_for_function('window.__charts_ready === true')
    page.wait_for_timeout(500)
    page.pdf(path=pdf, format='A4', print_background=True,
             margin={'top': '12mm', 'bottom': '12mm', 'left': '10mm', 'right': '10mm'})
    b.close()
print(f'PDF written to {pdf}')
"""


def render_pdf(out_dir):
    html, pdf = out_dir / 'index.html', out_dir / 'report.pdf'
    try:
        import playwright  # noqa: F401
        subprocess.run([sys.executable, '-c', PDF_SNIPPET, str(html.resolve()), str(pdf.resolve())],
                       check=True)
        return
    except ImportError:
        pass
    print('  local playwright not available, rendering PDF in gcb_playwright container')
    subprocess.run(['docker', 'run', '--rm', '-v', f"{out_dir.resolve()}:/report",
                    'greencoding/gcb_playwright:v21',
                    'python3', '-c', PDF_SNIPPET, '/report/index.html', '/report/report.pdf'],
                   check=True)


def default_uri():
    try:
        url = subprocess.run(['git', 'remote', 'get-url', 'origin'], capture_output=True,
                             text=True, check=True, cwd=Path(__file__).parent).stdout.strip()
        url = url.replace('git@github.com:', 'https://github.com/').removesuffix('.git')
        return url
    except subprocess.CalledProcessError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--api-url', default='https://api.green-coding.io')
    ap.add_argument('--uri', default=None, help='repo URI the runs were measured from (default: origin remote)')
    ap.add_argument('--scenarios', default=None, help='comma-separated subset, e.g. idle,browse')
    ap.add_argument('-o', '--out', default='report', help='output directory (default: report/)')
    ap.add_argument('--pdf', action='store_true', help='also render report.pdf')
    args = ap.parse_args()

    uri = args.uri or default_uri()
    if not uri:
        ap.error('no origin remote found; pass --uri')
    scenarios = set(args.scenarios.split(',')) if args.scenarios else None

    print(f"Listing runs for {uri} on {args.api_url}")
    runs = select_runs(args.api_url, uri, scenarios)
    if not runs:
        sys.exit('No successful runs found — check --uri/--api-url.')
    print(f"Selected {len(runs)} runs "
          f"({len({v for v, _ in runs})} versions x {len({s for _, s in runs})} scenarios)")

    data = collect(args.api_url, runs)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'index.html').write_text(build_html(data, args.api_url, uri))
    print(f"Web report written to {out_dir / 'index.html'}")
    if args.pdf:
        render_pdf(out_dir)


if __name__ == '__main__':
    main()
