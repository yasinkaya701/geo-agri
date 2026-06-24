import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from typing import Optional


# ─────────────────────────────────────────────────────
# Shared Plotly Theme Configuration
# ─────────────────────────────────────────────────────
PLOTLY_THEME = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(
        family="Inter, -apple-system, sans-serif",
        color="#334155",
        size=12,
    ),
    xaxis=dict(
        gridcolor="rgba(0,0,0,0.04)",
        linecolor="rgba(0,0,0,0.08)",
        zeroline=False,
        showgrid=True,
        tickfont=dict(size=11, color="#94A3B8"),
        title_font=dict(size=12, color="#64748B", weight="bold"),
    ),
    yaxis=dict(
        gridcolor="rgba(0,0,0,0.04)",
        linecolor="rgba(0,0,0,0.08)",
        zeroline=False,
        showgrid=True,
        tickfont=dict(size=11, color="#94A3B8"),
        title_font=dict(size=12, color="#64748B", weight="bold"),
    ),
    hovermode="x unified",
    hoverlabel=dict(
        bgcolor="#FFFFFF",
        bordercolor="#E2E8F0",
        font=dict(family="Inter, sans-serif", size=12, color="#1E293B"),
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.04,
        xanchor="right",
        x=1,
        font=dict(size=11, color="#64748B"),
        bgcolor="rgba(255,255,255,0)",
    ),
    margin=dict(l=40, r=24, t=56, b=40),
)

# Color palette
COLORS = {
    "primary": "#10B981",
    "primary_dark": "#047857",
    "primary_light": "#A7F3D0",
    "primary_fill": "rgba(16,185,129,0.08)",
    "blue": "#3B82F6",
    "blue_light": "rgba(59,130,246,0.1)",
    "slate": "#64748B",
    "red": "#EF4444",
    "amber": "#F59E0B",
}


def plot_ndvi_time_series(
    df: pd.DataFrame,
    df_interpolated: Optional[pd.DataFrame] = None,
    index_name: str = "NDVI",
) -> go.Figure:
    """Tarla ortalama spektral indeks zaman serisini gösteren premium grafik.

    Hem ham gözlemleri hem de enterpolasyonlu eğriyi gösterir.
    Area fill ile dolgu efekti ekler.
    """
    fig = go.Figure()
    y_col = f"Mean_{index_name}"

    # 1. Enterpolasyonlu alan dolgusu + eğri
    if df_interpolated is not None and not df_interpolated.empty and y_col in df_interpolated.columns:
        # Area fill
        fig.add_trace(
            go.Scatter(
                x=df_interpolated["Date"],
                y=df_interpolated[y_col],
                mode="lines",
                name=f"{index_name} Eğrisi (Düzleştirilmiş)",
                line=dict(color=COLORS["primary"], width=2.5, shape="spline"),
                fill="tozeroy",
                fillcolor=COLORS["primary_fill"],
                hoverinfo="skip",
            )
        )

    # 2. Ham gözlem noktaları
    if not df.empty and y_col in df.columns:
        marker_mode = "markers+lines" if df_interpolated is None else "markers"
        fig.add_trace(
            go.Scatter(
                x=df["Date"],
                y=df[y_col],
                mode=marker_mode,
                name="Gözlemler",
                marker=dict(
                    color=COLORS["blue"],
                    size=7,
                    line=dict(color="#FFFFFF", width=1.5),
                    symbol="circle",
                ),
                line=(
                    dict(color=COLORS["blue"], width=1.5)
                    if df_interpolated is None
                    else None
                ),
                hovertemplate=(
                    "<b>%{x|%d %b %Y}</b><br>"
                    + f"{index_name}: "
                    + "%{y:.3f}<br>"
                    + "Bulut: %{customdata:.1f}%"
                    + "<extra></extra>"
                ),
                customdata=df["Field_Cloud_Percent"],
            )
        )

    # 3. Sağlıklı vejetasyon bandı (yalnızca NDVI)
    if index_name == "NDVI":
        fig.add_hrect(
            y0=0.5,
            y1=1.0,
            fillcolor="rgba(16,185,129,0.04)",
            opacity=0.6,
            layer="below",
            line_width=0,
            annotation_text="Sağlıklı Bölge",
            annotation_position="top left",
            annotation_font=dict(size=10, color="rgba(16,185,129,0.45)"),
        )

    fig.update_layout(PLOTLY_THEME)
    fig.update_layout(
        title=dict(
            text=f"Tarihsel {index_name} Gelişim Eğrisi",
            y=0.96,
            x=0.02,
            xanchor="left",
            yanchor="top",
            font=dict(
                family="Space Grotesk, sans-serif",
                size=16,
                color="#0F172A",
                weight="bold",
            ),
        ),
        yaxis_range=[-0.2, 1.0],
        yaxis_title=f"{index_name} Değeri",
        xaxis_title="Tarih",
        height=380,
    )

    return fig


def plot_pixel_distribution(
    values: np.ndarray, date_str: str, index_name: str = "NDVI"
) -> go.Figure:
    """Piksel düzeyindeki dağılım histogramı — ortalama ve medyan çizgileri ile."""
    clean_values = values[~np.isnan(values)]

    fig = go.Figure()

    fig.add_trace(
        go.Histogram(
            x=clean_values,
            nbinsx=30,
            name="Pikseller",
            marker=dict(
                color=COLORS["primary"],
                line=dict(color=COLORS["primary_dark"], width=0.5),
            ),
            opacity=0.8,
            hovertemplate=(
                f"{index_name} Aralığı: " + "%{x}<br>Piksel Sayısı: %{y}<extra></extra>"
            ),
        )
    )

    # Ortalama çizgisi
    if len(clean_values) > 0:
        mean_val = float(np.mean(clean_values))
        median_val = float(np.median(clean_values))

        fig.add_vline(
            x=mean_val,
            line_width=2,
            line_dash="dash",
            line_color=COLORS["blue"],
            annotation_text=f"Ort: {mean_val:.2f}",
            annotation_position="top right",
            annotation_font=dict(size=10, color=COLORS["blue"]),
        )

        fig.add_vline(
            x=median_val,
            line_width=1.5,
            line_dash="dot",
            line_color=COLORS["amber"],
            annotation_text=f"Med: {median_val:.2f}",
            annotation_position="top left",
            annotation_font=dict(size=10, color=COLORS["amber"]),
        )

    fig.update_layout(PLOTLY_THEME)
    fig.update_layout(
        title=dict(
            text=f"Piksel {index_name} Dağılımı — {date_str}",
            font=dict(
                family="Space Grotesk, sans-serif",
                size=14,
                color="#0F172A",
                weight="bold",
            ),
        ),
        xaxis_title=f"{index_name} Değeri",
        xaxis_range=[-0.2, 1.0] if "ND" in index_name else [0.0, 1.0],
        yaxis_title="Frekans (Piksel)",
        height=280,
        bargap=0.06,
    )

    return fig
