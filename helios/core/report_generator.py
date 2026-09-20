"""
Comprehensive scientific report generator and telemetry briefing studio for HELIOS-L1.
Produces publication-grade HTML and Markdown reports summarizing space weather events,
sensor calibrations, CME shocks, and auroral forecasts.
"""
from datetime import datetime, timezone
from typing import Dict, List, Any

class ScientificReportGenerator:
    """Generates structured scientific bulletins and analysis summaries."""

    @classmethod
    def generate_html_bulletin(
        cls,
        mission_name: str,
        telemetry: List[Dict[str, Any]],
        classification: Dict[str, Any],
        shocks: List[Dict[str, Any]],
        auroral_data: Dict[str, Any]
    ) -> str:
        """Produce a complete, self-contained scientific HTML briefing document."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        latest = telemetry[-1] if telemetry else {}

        shocks_html = ""
        if shocks:
            for s in shocks:
                shocks_html += f"""
                <tr>
                    <td style="padding: 6px; border: 1px solid #334155; font-family: monospace;">{s['time']}</td>
                    <td style="padding: 6px; border: 1px solid #334155; color: #f43f5e; font-weight: bold;">{s['classification']}</td>
                    <td style="padding: 6px; border: 1px solid #334155; color: #38bdf8;">+{s['delta_speed_kms']} km/s</td>
                    <td style="padding: 6px; border: 1px solid #334155;">{s['density_ratio']}x</td>
                    <td style="padding: 6px; border: 1px solid #334155;">{s['magnetic_ratio']}x</td>
                    <td style="padding: 6px; border: 1px solid #334155; font-weight: bold;">{s['mach_proxy']}</td>
                </tr>
                """
        else:
            shocks_html = '<tr><td colspan="6" style="padding: 8px; text-align: center; color: #64748b; font-style: italic;">No CME shocks detected.</td></tr>'

        regions_html = "".join([f'<li style="color: #cbd5e1; margin-bottom: 2px;">{r}</li>' for r in auroral_data.get("visible_regions", [])])

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>HELIOS-L1 Scientific Space Weather Bulletin</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #060a12; color: #e2e8f0; margin: 0; padding: 24px; }}
  .container {{ max-width: 900px; margin: 0 auto; background: #0b1329; border: 1px solid #1e293b; border-radius: 12px; padding: 24px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
  h1 {{ color: #38bdf8; font-size: 22px; margin-top: 0; border-bottom: 1px solid #1e293b; padding-bottom: 12px; }}
  .badge {{ display: inline-block; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 12px; }}
  .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 16px 0; }}
  .card {{ background: #111e3e; border: 1px solid #1e293b; border-radius: 8px; padding: 12px; }}
  .card-label {{ color: #94a3b8; font-size: 11px; text-transform: uppercase; font-weight: bold; }}
  .card-value {{ font-size: 20px; font-weight: bold; margin-top: 4px; color: #f8fafc; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 12px; }}
  th {{ background: #172554; color: #94a3b8; text-align: left; padding: 8px; border: 1px solid #334155; }}
  .footer {{ margin-top: 24px; border-top: 1px solid #1e293b; padding-top: 12px; font-size: 11px; color: #64748b; }}
</style>
</head>
<body>
<div class="container">
  <div style="display: flex; justify-content: space-between; align-items: center;">
    <div>
      <h1>HELIOS-L1 Space Weather Scientific Bulletin</h1>
      <div style="color: #94a3b8; font-size: 12px;">Spacecraft: <strong>{mission_name}</strong> • Timestamp: {now_str}</div>
    </div>
    <div>
      <span class="badge" style="background: {classification.get('g_color', '#10b981')}22; color: {classification.get('g_color', '#10b981')}; border: 1px solid {classification.get('g_color', '#10b981')}66;">
        {classification.get('g_scale', 'G0 Quiet')}
      </span>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-label">Solar Wind Velocity</div>
      <div class="card-value">{latest.get('speed', '---')} <span style="font-size: 12px; color: #94a3b8;">km/s</span></div>
    </div>
    <div class="card">
      <div class="card-label">IMF Bz (GSM)</div>
      <div class="card-value" style="color: {classification.get('bz_color', '#10b981')}">{latest.get('bz_gsm', '---')} <span style="font-size: 12px; color: #94a3b8;">nT</span></div>
    </div>
    <div class="card">
      <div class="card-label">Dynamic Pressure</div>
      <div class="card-value">{latest.get('dynamic_pressure', '---')} <span style="font-size: 12px; color: #94a3b8;">nPa</span></div>
    </div>
    <div class="card">
      <div class="card-label">Magnetopause Standoff (R_mp)</div>
      <div class="card-value" style="color: #f59e0b;">{latest.get('magnetopause_re', '---')} <span style="font-size: 12px; color: #94a3b8;">R_E</span></div>
    </div>
    <div class="card">
      <div class="card-label">Akasofu Energy Coupling (ε)</div>
      <div class="card-value" style="color: #a855f7;">{latest.get('akasofu_gw', '---')} <span style="font-size: 12px; color: #94a3b8;">GW</span></div>
    </div>
    <div class="card">
      <div class="card-label">L1-to-Earth Propagation Delay</div>
      <div class="card-value" style="color: #06b6d4;">{latest.get('l1_travel_time_min', '---')} <span style="font-size: 12px; color: #94a3b8;">min</span></div>
    </div>
  </div>

  <h3 style="color: #38bdf8; font-size: 14px; margin-top: 20px;">Auroral Oval Equatorward Reach & Potential Visibility</h3>
  <div style="background: #111e3e; border: 1px solid #1e293b; border-radius: 8px; padding: 12px; font-size: 12px;">
    <div>Equatorward Midnight Magnetic Latitude: <strong>{auroral_data.get('equatorward_midnight_lat', '---')}°</strong></div>
    <div style="margin-top: 4px;">Estimated Hemispheric Power Index: <strong>{auroral_data.get('hemispheric_power_gw', '---')} GW</strong></div>
    <div style="margin-top: 8px; font-weight: bold; color: #94a3b8;">Geographic Regions with Auroral Sighting Probability:</div>
    <ul style="margin: 4px 0 0 16px; padding: 0;">
      {regions_html}
    </ul>
  </div>

  <h3 style="color: #38bdf8; font-size: 14px; margin-top: 20px;">Rankine-Hugoniot Interplanetary Shock Transients</h3>
  <table>
    <thead>
      <tr>
        <th>Timestamp</th>
        <th>Classification</th>
        <th>Velocity Jump (ΔV)</th>
        <th>Density Jump (N2/N1)</th>
        <th>Magnetic Jump (B2/B1)</th>
        <th>Mach Proxy</th>
      </tr>
    </thead>
    <tbody>
      {shocks_html}
    </tbody>
  </table>

  <div class="footer">
    Generated autonomously by HELIOS-L1 (Heliophysical Exploration, Lagrange-1 Interplanetary Observation & Space-weather Suite) v1.0.
  </div>
</div>
</body>
</html>"""
        return html
