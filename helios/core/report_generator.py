"""
Comprehensive scientific report generator and telemetry briefing studio for HELIOS-L1.
Produces publication-grade HTML and Markdown reports summarizing space weather events,
sensor calibrations, CME shocks, and auroral forecasts.
"""
import html as html_lib
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from helios import __version__


def _latest_valid(telemetry: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Newest record with speed and Bz present (the newest row is often a partial gap)."""
    for rec in reversed(telemetry or []):
        if rec.get("speed") is not None and rec.get("bz_gsm") is not None:
            return rec
    return telemetry[-1] if telemetry else {}


def _provenance_text(provenance: Optional[Dict[str, Any]]) -> str:
    if not provenance:
        return "not recorded"
    kind = str(provenance.get("kind", "unknown")).upper()
    return f"{kind} - {provenance.get('description', '')}".strip(" -")


class ScientificReportGenerator:
    """Generates structured scientific bulletins and analysis summaries."""

    @classmethod
    def generate_html_bulletin(
        cls,
        mission_name: str,
        telemetry: List[Dict[str, Any]],
        classification: Dict[str, Any],
        shocks: List[Dict[str, Any]],
        auroral_data: Dict[str, Any],
        provenance: Optional[Dict[str, Any]] = None
    ) -> str:
        """Produce a complete, self-contained scientific HTML briefing document."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        latest = _latest_valid(telemetry)
        provenance_text = _provenance_text(provenance)

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

        s_color = classification.get('s_color', '#10b981')
        s_scale = classification.get('s_scale', 'S0 (Nominal)')
        r_scale = classification.get('r_scale', 'R0 (None)')
        r_level = classification.get('r_level', 0)
        r_color = '#f59e0b' if r_level > 0 else '#10b981'

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>HELIOS-L1 Scientific Space Weather Bulletin</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #060a12; color: #e2e8f0; margin: 0; padding: 24px; }}
  .container {{ max-width: 900px; margin: 0 auto; background: #0b1329; border: 1px solid #1e293b; border-radius: 12px; padding: 24px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
  h1 {{ color: #38bdf8; font-size: 22px; margin-top: 0; border-bottom: 1px solid #1e293b; padding-bottom: 12px; }}
  .badge {{ display: inline-block; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 11px; font-family: monospace; }}
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
  <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
    <div>
      <h1>HELIOS-L1 Space Weather Scientific Bulletin</h1>
      <div style="color: #94a3b8; font-size: 12px;">Spacecraft: <strong>{mission_name}</strong> • Timestamp: {now_str}</div>
      <div style="color: #94a3b8; font-size: 12px;">Data provenance: {html_lib.escape(provenance_text)}</div>
    </div>
    <div style="display: flex; gap: 8px; align-items: center;">
      <span class="badge" style="background: {classification.get('g_color', '#10b981')}22; color: {classification.get('g_color', '#10b981')}; border: 1px solid {classification.get('g_color', '#10b981')}66;">
        {classification.get('g_scale', 'G0 Quiet')}
      </span>
      <span class="badge" style="background: {s_color}22; color: {s_color}; border: 1px solid {s_color}66;">
        {s_scale}
      </span>
      <span class="badge" style="background: {r_color}22; color: {r_color}; border: 1px solid {r_color}66;">
        {r_scale}
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
    Generated autonomously by HELIOS-L1 (Heliophysical Exploration, Lagrange-1 Interplanetary Observation & Space-weather Suite) v{__version__}.
  </div>
</div>
</body>
</html>"""
        return html

    @classmethod
    def generate_markdown_executive_summary(
        cls,
        mission_name: str,
        telemetry: List[Dict[str, Any]],
        classification: Dict[str, Any],
        shocks: List[Dict[str, Any]],
        auroral_data: Dict[str, Any],
        provenance: Optional[Dict[str, Any]] = None
    ) -> str:
        """Produce a publication-grade Markdown Executive Summary suitable for command briefing and archiving."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        latest = _latest_valid(telemetry)
        provenance_text = _provenance_text(provenance)

        def get_stats(field: str, decimals: int = 1):
            vals = [float(r[field]) for r in telemetry if field in r and isinstance(r[field], (int, float))]
            if not vals:
                return "---", "---", "---"
            return (
                f"{min(vals):.{decimals}f}",
                f"{(sum(vals) / len(vals)):.{decimals}f}",
                f"{max(vals):.{decimals}f}"
            )

        v_min, v_avg, v_max = get_stats("speed", 1)
        bz_min, bz_avg, bz_max = get_stats("bz_gsm", 1)
        bt_min, bt_avg, bt_max = get_stats("bt", 1)
        n_min, n_avg, n_max = get_stats("density", 1)
        p_min, p_avg, p_max = get_stats("dynamic_pressure", 2)
        lead_min, lead_avg, lead_max = get_stats("l1_travel_time_min", 1)

        g_scale = classification.get("g_scale", "G0 (Quiet)")
        s_scale = classification.get("s_scale", "S0 (Nominal)")
        r_scale = classification.get("r_scale", "R0 (None)")
        proton_pfu = classification.get("proton_flux_pfu")
        if proton_pfu is None:
            proton_pfu = "n/a"
        flare_cls = classification.get("flare_class", "Quiet")

        bz_val = latest.get("bz_gsm")
        if bz_val is None:
            reconn_status = "UNKNOWN (no IMF Bz in the latest records)"
        elif bz_val < 0:
            reconn_status = "ACTIVE RECONNECTION (Southward IMF Bz < 0)"
        else:
            reconn_status = "CLOSED MAGNETOSPHERE (Northward IMF Bz >= 0)"

        shocks_table = ""
        if shocks:
            shocks_table = "| Timestamp (UTC) | Shock Type | Velocity Jump (ΔV) | Density Ratio (N₂/N₁) | Field Ratio (B₂/B₁) | Mach Number |\n"
            shocks_table += "|---|---|---|---|---|---|\n"
            for s in shocks:
                shocks_table += f"| `{s.get('time', '---')}` | **{s.get('classification', 'Shock')}** | +{s.get('delta_speed_kms', 0)} km/s | {s.get('density_ratio', 1.0)}x | {s.get('magnetic_ratio', 1.0)}x | M = {s.get('mach_proxy', 1.0)} |\n"
        else:
            shocks_table = "_No Rankine-Hugoniot interplanetary shock discontinuities detected in the current 24-hour observation window._\n"

        regions = auroral_data.get("visible_regions", [])
        regions_str = ", ".join(regions) if regions else "Polar caps only (> 75° Magnetic Latitude)"

        md = f"""# HELIOS-L1 SPACE WEATHER EXECUTIVE SUMMARY
**Mission Platform:** {mission_name}  
**Report Timestamp:** {now_str}  
**Data Provenance:** {provenance_text}  
**Standard License:** Open Scientific Data (NASA / NOAA Open Access & ISRO Open Science)

---

## 1. OPERATIONAL ALERT POSTURE & NOAA SCALES
- **Geomagnetic Storm Activity (G-Scale):** `{g_scale}`
- **Solar Radiation Storm Activity (S-Scale):** `{s_scale}` (Proton Flux ≥ 10 MeV: **{proton_pfu} pfu**)
- **HF Radio Blackout Activity (R-Scale):** `{r_scale}` (X-ray Flare Class: **{flare_cls}**)
- **Interplanetary Reconnection State:** **{reconn_status}**
- **Magnetopause Subsolar Standoff ($R_{{mp}}$):** **{latest.get('magnetopause_re', '---')} $R_E$** (Nominal ~ 10–11 $R_E$)
- **Akasofu Energy Coupling (ε / \\epsilon):** **{latest.get('akasofu_gw', '---')} GW**

---

## 2. 24-HOUR SYNOPTIC TELEMETRY EXTREMA
| Observable Parameter | Current Reading | 24h Minimum | 24h Mean | 24h Maximum | Units |
|---|---|---|---|---|---|
| Bulk Solar Wind Velocity ($v_{{sw}}$) | **{latest.get('speed', '---')}** | {v_min} | {v_avg} | {v_max} | km/s |
| Interplanetary Field $B_z$ (GSM) | **{latest.get('bz_gsm', '---')}** | {bz_min} | {bz_avg} | {bz_max} | nT |
| Total Magnetic Field ($|B|$) | **{latest.get('bt', '---')}** | {bt_min} | {bt_avg} | {bt_max} | nT |
| Proton Plasma Density ($n_p$) | **{latest.get('density', '---')}** | {n_min} | {n_avg} | {n_max} | cm⁻³ |
| Solar Wind Dynamic Pressure ($P_{{dyn}}$) | **{latest.get('dynamic_pressure', '---')}** | {p_min} | {p_avg} | {p_max} | nPa |
| L1 $\\rightarrow$ Earth Propagation Lead Time | **{latest.get('l1_travel_time_min', '---')}** | {lead_min} | {lead_avg} | {lead_max} | minutes |

---

## 3. RANKINE-HUGONIOT INTERPLANETARY SHOCK TRANSIENTS
{shocks_table}

---

## 4. GEOSPACE HAZARD & AURORAL REACH ASSESSMENT
- **Equatorward Midnight Magnetic Latitude:** **{auroral_data.get('equatorward_midnight_lat', '---')}° MLAT**
- **Estimated Hemispheric Power Index (HPI):** **{auroral_data.get('hemispheric_power_gw', '---')} GW**
- **Potential Visual Auroral Sighting Sectors:** {regions_str}

---

## 5. REFERRED SCIENTIFIC FORMULATIONS & CITATIONS
1. **Rankine-Hugoniot Magnetohydrodynamic Shock Jump Conditions:** Viñas, A. F., & Scudder, J. D. (1986). *JGR Space Physics*, 91(A1), 39–58.
2. **Dynamic Drag Deceleration CME Model:** Gopalswamy, N., et al. (2001). *JGR Space Physics*, 106(A12), 29207–29217.
3. **Akasofu Energy Coupling Function (ε / \\epsilon):** Perreault, P., & Akasofu, S.-I. (1978). *Geophysical Journal International*, 54(3), 547–573.
4. **Shue et al. Magnetopause Standoff ($R_{{mp}}$):** Shue, J.-H., et al. (1998). *JGR Space Physics*, 103(A8), 17691–17700.

---
*Report autonomously generated by HELIOS-L1 (Heliophysical Exploration, Lagrange-1 Interplanetary Observation & Space-weather Suite) v1.0.*
"""
        return md

