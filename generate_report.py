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
otherwise the greencoding/gcb_playwright container (needs docker). If pypdf
is installed, the PDF also gets a bookmarks/outline pane (one entry per
scenario). Per-run phase stats are cached under .report_cache/ (--no-cache
to disable, --cache-dir to relocate) since a completed run's stats never
change.
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

# Energy/power/carbon metrics are reported net of the machine's [BASELINE]
# idle consumption so versions stay comparable across machines and runs.
# label -> display unit (also fixes chart/table ordering)
DISPLAY_METRICS = [
    ('Server-side energy (xwiki+db)',      'J'),
    ('Machine energy above baseline',      'J'),
    ('Avg. machine power above baseline',  'W'),
    ('CPU package energy above baseline',  'J'),
    ('Operational carbon above baseline',  'mgCO2e'),
    ('Runtime duration',                   's'),
    ('CPU utilization',                    '%'),
    ('XWiki container memory',             'MB'),
    ('Network traffic',                    'MB'),
]
ATTRIBUTION_METRIC = 'psu_energy_cgroup_container'   # per-container energy split (sums to total machine energy)


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
        # keep the most recent successful run for each (version, scenario);
        # compare created_at explicitly rather than trusting the API's row
        # order (ISO-8601 timestamps sort lexicographically)
        prev = selected.get(key)
        if prev is None or created_at > prev['created_at']:
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


def fetch_phase_stats(api_url, run_id, cache_dir):
    """Phase stats of a completed run never change, so they're cached to disk
    forever once fetched; only newly-selected run ids cost an API call."""
    cache_file = cache_dir / f"{run_id}.json" if cache_dir else None
    if cache_file and cache_file.exists():
        return json.loads(cache_file.read_text()), True
    data = api_get(api_url, f"/v1/phase_stats/single/{run_id}")
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(data))
    return data, False


def collect(api_url, runs, cache_dir=None):
    """-> {(version, scenario): {'metrics': {label: value}, 'attribution': {container: J}, run meta}}"""
    out = {}
    for (version, scenario), meta in sorted(runs.items()):
        resp, cached = fetch_phase_stats(api_url, meta['id'], cache_dir)
        print(f"  fetching phase stats: xwiki-{version} {scenario} ({meta['id']})"
              + (" [cached]" if cached else ""))
        stats = resp['data']['data']
        runtime = stats.get('[RUNTIME]', {}).get('data', {})
        baseline = stats.get('[BASELINE]', {}).get('data', {})
        raw = lambda metric, detail='first', src=runtime: extract_value(src, metric, detail)

        dur_us = raw('phase_time_syscall_system')
        # baseline powers in mW; mW * us / 1000 = uJ over the runtime phase
        psu_base_mw = raw('psu_power_ac_mcp_machine', src=baseline) or 0
        cpu_base_mw = raw('cpu_power_rapl_msr_component', src=baseline) or 0
        e_total_uj = raw('psu_energy_ac_mcp_machine')
        e_surplus_uj = None if e_total_uj is None else e_total_uj - psu_base_mw * dur_us / 1000
        cpu_e_uj = raw('cpu_energy_rapl_msr_component')
        carbon_ug = raw('psu_carbon_ac_mcp_machine')

        # GMT splits the *total* machine energy over containers by CPU share;
        # rescale to the surplus so the baseline floor stays with the host
        attribution = {}
        for container, d in runtime.get(ATTRIBUTION_METRIC, {}).get('data', {}).items():
            attribution[container] = next(iter(d['data'].values()))['mean'] / 1e6
        attr_sum = sum(attribution.values())
        if attr_sum and e_surplus_uj is not None:
            scale = (e_surplus_uj / 1e6) / attr_sum
            attribution = {k: round(v * scale, 2) for k, v in attribution.items()}

        def r(value, div=1):
            return None if value is None else round(value / div, 2)

        values = {
            # excludes the load-generating browser container and GMT overhead
            'Server-side energy (xwiki+db)': r((attribution.get('xwiki') or 0) + (attribution.get('db') or 0))
                                             if 'xwiki' in attribution else None,
            'Machine energy above baseline': r(e_surplus_uj, 1e6),
            'Avg. machine power above baseline': r((raw('psu_power_ac_mcp_machine') or 0) - psu_base_mw, 1e3)
                                                 if raw('psu_power_ac_mcp_machine') is not None else None,
            'CPU package energy above baseline': r(None if cpu_e_uj is None else cpu_e_uj - cpu_base_mw * dur_us / 1000, 1e6),
            # scale total carbon by the surplus share (intensity is constant within a run)
            'Operational carbon above baseline': r(None if carbon_ug is None or not e_total_uj
                                                   else carbon_ug * e_surplus_uj / e_total_uj, 1e3),
            'Runtime duration': r(dur_us, 1e6),
            'CPU utilization': r(raw('cpu_utilization_procfs_system'), 1e2),
            'XWiki container memory': r(raw('memory_used_cgroup_container', 'xwiki'), 1e6),
            'Network traffic': r(raw('network_total_cgroup_container', 'sum'), 1e6),
        }
        out[(version, scenario)] = {**meta, 'metrics': values, 'attribution': attribution}
    return out


def render_nav(all_scenarios, current=None):
    crumbs = ['<span class="current">Overview</span>' if current is None
              else '<a href="index.html">Overview</a>']
    for s in all_scenarios:
        crumbs.append(f'<span class="current">{s}</span>' if s == current
                      else f'<a href="{s}.html">{s}</a>')
    return '<nav class="scenario-nav">' + ' · '.join(crumbs) + '</nav>'


def render_index_links(all_scenarios):
    items = ''.join(f'<li><a href="{s}.html">{s}</a></li>' for s in all_scenarios)
    return f'<h2>Scenarios</h2>\n<ul class="scenario-list">{items}</ul>'


def build_html(data, api_url, uri, *, chart_scenarios=None, table_scenarios=None,
               heading=None, extra_html=''):
    """Render one HTML page. By default includes every scenario's charts and
    the full runs table; pass chart_scenarios/table_scenarios subsets to
    build a scenario sub-page or a chart-less index/landing page."""
    versions = sorted({v for v, _ in data}, key=version_key)
    all_scenarios = sorted({s for _, s in data})
    chart_scenarios = all_scenarios if chart_scenarios is None else chart_scenarios
    table_scenarios = all_scenarios if table_scenarios is None else table_scenarios
    units = dict(DISPLAY_METRICS)
    heading = heading or 'XWiki across versions — Green Metrics Tool report'

    series_per_metric = {}
    for label, _ in DISPLAY_METRICS:
        series_per_metric[label] = {
            s: [data.get((v, s), {}).get('metrics', {}).get(label) for v in versions]
            for s in chart_scenarios
        }
    attribution = {
        s: {v: data.get((v, s), {}).get('attribution', {}) for v in versions}
        for s in chart_scenarios
    }
    table = [
        {'version': v, 'scenario': s, 'id': d['id'], 'machine': d['machine'],
         'commit': (d['commit'] or '')[:8], 'created_at': d['created_at'][:16],
         **{label: val for label, val in d['metrics'].items()}}
        for (v, s), d in sorted(data.items(), key=lambda kv: (version_key(kv[0][0]), kv[0][1]))
        if s in table_scenarios
    ]
    payload = json.dumps({'versions': versions, 'scenarios': chart_scenarios,
                          'units': units, 'metrics': series_per_metric,
                          'attribution': attribution, 'table': table,
                          'dashboard': api_url.replace('api.', 'metrics.')})
    generated = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{heading}</title>
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
  .scenario-nav {{ font-size: .9rem; margin: .5rem 0 1.2rem; }}
  .scenario-nav .current {{ font-weight: 600; color: #222; }}
  .scenario-list {{ columns: 2; }}
  @media print {{
    .grid {{ grid-template-columns: 1fr 1fr; }}
    .chart {{ height: 280px; }}
    h2 {{ break-before: auto; }} .chart, table {{ break-inside: avoid; }}
    .scenario-nav {{ display: none; }}
  }}
</style>
</head>
<body>
<h1>{heading}</h1>
<p class="meta">Repository: {uri} · Source: {api_url} · Generated: {generated}<br>
Latest successful run per version/scenario, metrics from the measured <code>[RUNTIME]</code> phase.</p>
{render_nav(all_scenarios, current=chart_scenarios[0] if len(chart_scenarios) == 1 else None)}
{extra_html}

<div id="scenario-sections"></div>

<h2>Runs included</h2>
<div id="table"></div>

<p class="footnote">Energy, power and carbon are reported net of the machine's idle
baseline (measured in each run's <code>[BASELINE]</code> phase) so values reflect the
workload, not the host. The attribution charts and "Server-side energy" split that
baseline-corrected energy over containers by CPU share; "Server-side energy" sums
xwiki+db, excluding the load-generating browser container (a simulated client on server
hardware) and GMT overhead — the browser's share remains visible in the attribution
charts. Operational carbon uses the live grid
intensity at the time of each run (electricitymaps), so carbon values are not directly
comparable across runs — compare energy instead. Memory/CPU/network are means or totals
over the runtime phase.</p>

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


def add_pdf_outline(pdf_path, scenarios):
    """Add a bookmarks pane to the PDF: one entry per scenario section plus
    the runs table. Page numbers aren't known ahead of Chromium's print, so
    each heading's page is found after the fact by searching extracted text."""
    try:
        import pypdf
    except ImportError:
        print('  pypdf not installed, skipping PDF outline/bookmarks (pip/apt install pypdf)')
        return
    reader = pypdf.PdfReader(str(pdf_path))
    headings = [(s, f'Scenario: {s} — evolution across versions') for s in scenarios]
    headings.append(('Runs included', 'Runs included'))
    writer = pypdf.PdfWriter()
    writer.append(reader)
    cursor = 0
    for title, needle in headings:
        for i in range(cursor, len(reader.pages)):
            if needle in reader.pages[i].extract_text():
                writer.add_outline_item(title, i)
                cursor = i
                break
    tmp = pdf_path.with_suffix('.tmp.pdf')
    with open(tmp, 'wb') as f:
        writer.write(f)
    tmp.replace(pdf_path)


def render_pdf(out_dir, html_content, scenarios):
    """Render html_content (the all-scenarios single-page report) to report.pdf.
    Kept as one page for print since no PDF-merge library is installed."""
    html = out_dir / '_print.html'
    pdf = out_dir / 'report.pdf'
    html.write_text(html_content)
    try:
        try:
            import playwright  # noqa: F401
            has_local_playwright = True
        except ImportError:
            has_local_playwright = False
        if has_local_playwright:
            subprocess.run([sys.executable, '-c', PDF_SNIPPET, str(html.resolve()), str(pdf.resolve())],
                           check=True)
        else:
            print('  local playwright not available, rendering PDF in gcb_playwright container')
            subprocess.run(['docker', 'run', '--rm', '-v', f"{out_dir.resolve()}:/report",
                            'greencoding/gcb_playwright:v21',
                            'python3', '-c', PDF_SNIPPET, f'/report/{html.name}', '/report/report.pdf'],
                           check=True)
    finally:
        html.unlink(missing_ok=True)
    add_pdf_outline(pdf, scenarios)


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
    ap.add_argument('--cache-dir', default='.report_cache',
                    help='on-disk cache for per-run phase stats, which never change once a run '
                         'completes (default: .report_cache/)')
    ap.add_argument('--no-cache', action='store_true', help='disable the phase-stats cache, always refetch')
    args = ap.parse_args()

    uri = args.uri or default_uri()
    if not uri:
        ap.error('no origin remote found; pass --uri')
    scenarios = set(args.scenarios.split(',')) if args.scenarios else None
    cache_dir = None if args.no_cache else Path(args.cache_dir)

    print(f"Listing runs for {uri} on {args.api_url}")
    runs = select_runs(args.api_url, uri, scenarios)
    if not runs:
        sys.exit('No successful runs found — check --uri/--api-url.')
    print(f"Selected {len(runs)} runs "
          f"({len({v for v, _ in runs})} versions x {len({s for _, s in runs})} scenarios)")

    data = collect(args.api_url, runs, cache_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_scenarios = sorted({s for _, s in data})

    index_heading = 'XWiki across versions — Green Metrics Tool report'
    index_html = build_html(data, args.api_url, uri, chart_scenarios=[],
                            heading=index_heading, extra_html=render_index_links(all_scenarios))
    (out_dir / 'index.html').write_text(index_html)

    for s in all_scenarios:
        page_html = build_html(data, args.api_url, uri, chart_scenarios=[s], table_scenarios=[s],
                               heading=f'XWiki — {s} — Green Metrics Tool report')
        (out_dir / f'{s}.html').write_text(page_html)

    print(f"Web report written to {out_dir} (index.html + {len(all_scenarios)} scenario pages)")
    if args.pdf:
        full_html = build_html(data, args.api_url, uri)
        render_pdf(out_dir, full_html, all_scenarios)


if __name__ == '__main__':
    main()
