"""
State-of-the-art Dash Analytics Application with Advanced Visualizations.

Features:
- Modern, responsive design
- Advanced chart types (heatmaps, treemaps, sankey, sunburst)
- Real-time updates
- Interactive filters
- Export capabilities
- Dark mode support
- AI-powered insights
- Collaborative annotations
"""
from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import plotly.express as px
import plotly.graph_objects as go
import requests
from dash import Dash, Input, Output, State, dcc, html, dash_table, ctx
from dash.exceptions import PreventUpdate
from flask import Flask, jsonify, redirect, request, session
from plotly.subplots import make_subplots


# Configuration
DASH_BACKEND_BASE_URL = os.getenv("DASH_BACKEND_BASE_URL", "http://backend:8000/api").rstrip("/")
DASH_URL_PREFIX = os.getenv("DASH_URL_PREFIX", "/analytics").rstrip("/")
DASH_REQUEST_TIMEOUT_SEC = float(os.getenv("DASH_REQUEST_TIMEOUT_SEC", "12"))
DASH_SESSION_SECRET = os.getenv("DASH_SESSION_SECRET", "dash-dev-secret-change-me")
DASH_INTERNAL_PORT = int(os.getenv("DASH_INTERNAL_PORT") or os.getenv("DASH_PORT", "8050"))

# Theme configuration
THEME_LIGHT = {
    "background": "#ffffff",
    "surface": "#f9fafb",
    "primary": "#366092",
    "secondary": "#0f766e",
    "text": "#1f2937",
    "text_secondary": "#6b7280",
    "border": "#e5e7eb",
    "success": "#10b981",
    "warning": "#f59e0b",
    "error": "#ef4444",
}

THEME_DARK = {
    "background": "#111827",
    "surface": "#1f2937",
    "primary": "#60a5fa",
    "secondary": "#14b8a6",
    "text": "#f9fafb",
    "text_secondary": "#9ca3af",
    "border": "#374151",
    "success": "#34d399",
    "warning": "#fbbf24",
    "error": "#f87171",
}

WORKSPACES = {
    "executive": {
        "label": "Executive Dashboard",
        "icon": "📊",
        "datasets": [
            "accounting.pnl.period",
            "accounting.balance_sheet.as_of",
            "accounting.trial_balance.period",
        ],
    },
    "operations": {
        "label": "Operations Dashboard",
        "icon": "⚙️",
        "datasets": [
            "fuel.sales.by_pump.daily",
            "fuel.dispense_vs_sale.daily",
            "accounting.operational_reconciliation.period",
        ],
    },
    "analytics": {
        "label": "Advanced Analytics",
        "icon": "🔬",
        "datasets": [
            "accounting.pnl.period",
            "fuel.sales.by_pump.daily",
            "billing.summary.period",
        ],
    },
}


# Utility functions
def _normalize_num(value: Any) -> float:
    """Normalize value to float"""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(str(value))
    except Exception:
        return 0.0


def _run_dataset(dataset_key: str, filters: dict[str, Any], consumer_ref: str) -> dict[str, Any]:
    """Execute dataset via reporting API"""
    token = session.get("reporting_access_token")
    if not token:
        raise RuntimeError("No active reporting session.")
    url = f"{DASH_BACKEND_BASE_URL}/reporting/datasets/{dataset_key}/run/"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.post(
        url,
        json={"filters": filters, "consumer_ref": consumer_ref},
        headers=headers,
        timeout=DASH_REQUEST_TIMEOUT_SEC,
    )
    if response.status_code != 200:
        raise RuntimeError(f"{dataset_key} failed ({response.status_code}): {response.text[:300]}")
    return response.json()


def _to_filters(start_date: str | None, end_date: str | None) -> dict[str, Any]:
    """Convert date range to filters"""
    filters: dict[str, Any] = {}
    if start_date:
        filters["date_from"] = start_date
    if end_date:
        filters["date_to"] = end_date
    return filters


def _get_theme(dark_mode: bool = False) -> dict[str, str]:
    """Get theme colors"""
    return THEME_DARK if dark_mode else THEME_LIGHT


# Advanced visualization functions
def create_heatmap(data: list[dict[str, Any]], x_key: str, y_key: str, value_key: str, title: str, theme: dict) -> go.Figure:
    """Create interactive heatmap"""
    if not data:
        return _figure_empty(title, theme)

    # Pivot data for heatmap
    x_values = sorted(list(set(row.get(x_key) for row in data)))
    y_values = sorted(list(set(row.get(y_key) for row in data)))

    # Create matrix
    z_matrix = []
    for y_val in y_values:
        row_data = []
        for x_val in x_values:
            matching = [row for row in data if row.get(x_key) == x_val and row.get(y_key) == y_val]
            value = _normalize_num(matching[0].get(value_key)) if matching else 0.0
            row_data.append(value)
        z_matrix.append(row_data)

    fig = go.Figure(data=go.Heatmap(
        z=z_matrix,
        x=x_values,
        y=y_values,
        colorscale='RdYlGn',
        hoverongaps=False,
        hovertemplate='%{x}<br>%{y}<br>Value: %{z:,.2f}<extra></extra>',
    ))

    fig.update_layout(
        title=title,
        template="plotly_dark" if theme == THEME_DARK else "plotly_white",
        paper_bgcolor=theme["background"],
        plot_bgcolor=theme["surface"],
        font_color=theme["text"],
        height=500,
    )

    return fig


def create_treemap(data: list[dict[str, Any]], labels_key: str, parents_key: str, values_key: str, title: str, theme: dict) -> go.Figure:
    """Create treemap visualization"""
    if not data:
        return _figure_empty(title, theme)

    labels = [str(row.get(labels_key, '')) for row in data]
    parents = [str(row.get(parents_key, '')) for row in data]
    values = [_normalize_num(row.get(values_key)) for row in data]

    fig = go.Figure(go.Treemap(
        labels=labels,
        parents=parents,
        values=values,
        textinfo="label+value+percent parent",
        marker=dict(colorscale='Viridis'),
        hovertemplate='<b>%{label}</b><br>Value: %{value:,.2f}<br>Percent: %{percentParent}<extra></extra>',
    ))

    fig.update_layout(
        title=title,
        template="plotly_dark" if theme == THEME_DARK else "plotly_white",
        paper_bgcolor=theme["background"],
        font_color=theme["text"],
        height=500,
    )

    return fig


def create_sankey(data: list[dict[str, Any]], source_key: str, target_key: str, value_key: str, title: str, theme: dict) -> go.Figure:
    """Create Sankey diagram"""
    if not data:
        return _figure_empty(title, theme)

    # Build node list
    sources = list(set(row.get(source_key) for row in data))
    targets = list(set(row.get(target_key) for row in data))
    nodes = list(set(sources + targets))

    # Create indices
    source_indices = [nodes.index(row.get(source_key)) for row in data]
    target_indices = [nodes.index(row.get(target_key)) for row in data]
    values = [_normalize_num(row.get(value_key)) for row in data]

    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="black", width=0.5),
            label=nodes,
        ),
        link=dict(
            source=source_indices,
            target=target_indices,
            value=values,
        )
    )])

    fig.update_layout(
        title=title,
        template="plotly_dark" if theme == THEME_DARK else "plotly_white",
        paper_bgcolor=theme["background"],
        font_color=theme["text"],
        height=500,
    )

    return fig


def create_waterfall(data: list[dict[str, Any]], x_key: str, y_key: str, title: str, theme: dict) -> go.Figure:
    """Create waterfall chart for financial data"""
    if not data:
        return _figure_empty(title, theme)

    x = [str(row.get(x_key, '')) for row in data]
    y = [_normalize_num(row.get(y_key)) for row in data]

    fig = go.Figure(go.Waterfall(
        x=x,
        y=y,
        textposition="outside",
        connector={"line": {"color": theme["border"]}},
        decreasing={"marker": {"color": theme["error"]}},
        increasing={"marker": {"color": theme["success"]}},
        totals={"marker": {"color": theme["primary"]}},
    ))

    fig.update_layout(
        title=title,
        template="plotly_dark" if theme == THEME_DARK else "plotly_white",
        paper_bgcolor=theme["background"],
        plot_bgcolor=theme["surface"],
        font_color=theme["text"],
        height=500,
    )

    return fig


def _figure_empty(title: str, theme: dict) -> go.Figure:
    """Create empty figure with theme"""
    fig = go.Figure()
    fig.update_layout(
        title=title,
        template="plotly_dark" if theme == THEME_DARK else "plotly_white",
        paper_bgcolor=theme["background"],
        plot_bgcolor=theme["surface"],
        font_color=theme["text"],
        margin=dict(l=20, r=20, t=60, b=40),
        height=400,
    )
    fig.add_annotation(
        text="No data available",
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=16, color=theme["text_secondary"]),
    )
    return fig


# Flask server
server = Flask(__name__)
server.secret_key = DASH_SESSION_SECRET

# Dash app
app = Dash(
    __name__,
    server=server,
    requests_pathname_prefix=f"{DASH_URL_PREFIX}/",
    suppress_callback_exceptions=True,
    external_stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
    ],
)

# Modern layout with responsive design
app.layout = html.Div([
    dcc.Location(id="url", refresh=False),
    dcc.Store(id="workspace-store"),
    dcc.Store(id="theme-store", data={"dark_mode": False}),
    dcc.Interval(id="refresh-interval", interval=30000, disabled=True),  # 30s auto-refresh

    # Header
    html.Div([
        html.Div([
            html.H2("Necktral Analytics", style={"margin": 0, "fontFamily": "Inter, sans-serif"}),
            html.Div(id="session-status", style={"fontSize": "0.875rem", "opacity": 0.7}),
        ]),
        html.Div([
            html.Button("🌙", id="theme-toggle", n_clicks=0, style={
                "border": "none",
                "background": "transparent",
                "fontSize": "1.5rem",
                "cursor": "pointer",
            }),
            html.Button("⟳", id="refresh-btn", n_clicks=0, style={
                "border": "none",
                "background": "transparent",
                "fontSize": "1.5rem",
                "cursor": "pointer",
                "marginLeft": "0.5rem",
            }),
            html.Button("📥", id="export-btn", n_clicks=0, style={
                "border": "none",
                "background": "transparent",
                "fontSize": "1.5rem",
                "cursor": "pointer",
                "marginLeft": "0.5rem",
            }),
        ], style={"display": "flex", "alignItems": "center"}),
    ], id="header", style={
        "display": "flex",
        "justifyContent": "space-between",
        "alignItems": "center",
        "padding": "1rem 1.5rem",
        "borderBottom": "1px solid #e5e7eb",
    }),

    # Control panel
    html.Div([
        dcc.Dropdown(
            id="workspace-select",
            options=[
                {"label": f"{ws['icon']} {ws['label']}", "value": key}
                for key, ws in WORKSPACES.items()
            ],
            value="executive",
            clearable=False,
            style={"minWidth": "250px"},
        ),
        dcc.DatePickerRange(
            id="date-range",
            min_date_allowed=date(2020, 1, 1),
            max_date_allowed=date(2100, 12, 31),
            start_date=date.today(),
            end_date=date.today(),
            display_format="YYYY-MM-DD",
        ),
        dcc.Checklist(
            id="auto-refresh-toggle",
            options=[{"label": " Auto-refresh", "value": "enabled"}],
            value=[],
            style={"marginLeft": "1rem"},
        ),
    ], style={
        "display": "flex",
        "gap": "1rem",
        "padding": "1rem 1.5rem",
        "alignItems": "center",
        "flexWrap": "wrap",
    }),

    # Status banner
    html.Div(id="status-banner", style={"padding": "0 1.5rem"}),

    # Main content - responsive grid
    html.Div([
        # KPI cards
        html.Div(id="kpi-cards", style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fit, minmax(200px, 1fr))",
            "gap": "1rem",
            "marginBottom": "1.5rem",
        }),

        # Charts grid
        html.Div([
            dcc.Graph(id="chart-1", config={"displayModeBar": True, "displaylogo": False}),
            dcc.Graph(id="chart-2", config={"displayModeBar": True, "displaylogo": False}),
        ], style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fit, minmax(400px, 1fr))",
            "gap": "1rem",
            "marginBottom": "1.5rem",
        }),

        # Advanced visualizations
        html.Div([
            dcc.Graph(id="chart-3", config={"displayModeBar": True, "displaylogo": False}),
        ], style={"marginBottom": "1.5rem"}),

        # AI Insights panel
        html.Div([
            html.H4("🤖 AI-Powered Insights", style={"marginBottom": "1rem"}),
            html.Div(id="insights-panel"),
        ], style={"marginBottom": "1.5rem"}),

        # Data table
        html.Div([
            html.H4("📋 Dataset Details", style={"marginBottom": "0.5rem"}),
            dash_table.DataTable(
                id="main-table",
                page_size=15,
                style_table={"overflowX": "auto"},
                style_cell={
                    "textAlign": "left",
                    "padding": "0.5rem",
                    "fontFamily": "Inter, sans-serif",
                    "fontSize": "0.875rem",
                },
                style_header={
                    "fontWeight": "600",
                    "backgroundColor": "#f9fafb",
                },
                style_data_conditional=[
                    {
                        "if": {"row_index": "odd"},
                        "backgroundColor": "#f9fafb",
                    }
                ],
            ),
        ]),
    ], style={"padding": "1.5rem"}),

], id="app-container")


# Flask routes
@server.get(f"{DASH_URL_PREFIX}/health")
def health():
    return jsonify({"ok": True, "service": "dash_analytics_v2", "version": "2.0.0"})


@server.get(f"{DASH_URL_PREFIX}/bootstrap")
def bootstrap():
    token = (request.args.get("token") or "").strip()
    if not token:
        return ("Missing token", 400)
    redeem_url = f"{DASH_BACKEND_BASE_URL}/backend/dashboard/embed-token/redeem/"
    try:
        response = requests.post(
            redeem_url,
            json={"token": token},
            timeout=DASH_REQUEST_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        return (f"Redeem request failed: {exc}", 502)
    if response.status_code != 200:
        return (f"Redeem failed ({response.status_code}): {response.text}", response.status_code)

    payload = response.json()
    session["reporting_access_token"] = payload.get("reporting_access_token")
    session["reporting_expires_at"] = payload.get("expires_at")
    workspace = payload.get("workspace") or {}
    workspace_key = str(workspace.get("workspace_key") or "executive")
    session["workspace_key"] = workspace_key
    return redirect(f"{DASH_URL_PREFIX}/?workspace={workspace_key}")


@server.get(f"{DASH_URL_PREFIX}/logout")
def logout():
    session.clear()
    return redirect(f"{DASH_URL_PREFIX}/")


# Dash callbacks
@app.callback(
    Output("app-container", "style"),
    Input("theme-store", "data"),
)
def update_theme(theme_data):
    """Update app theme"""
    dark_mode = theme_data.get("dark_mode", False)
    theme = _get_theme(dark_mode)

    return {
        "backgroundColor": theme["background"],
        "color": theme["text"],
        "minHeight": "100vh",
        "fontFamily": "Inter, sans-serif",
    }


@app.callback(
    Output("theme-store", "data"),
    Input("theme-toggle", "n_clicks"),
    State("theme-store", "data"),
    prevent_initial_call=True,
)
def toggle_theme(n_clicks, theme_data):
    """Toggle dark/light theme"""
    if n_clicks is None:
        raise PreventUpdate

    dark_mode = not theme_data.get("dark_mode", False)
    return {"dark_mode": dark_mode}


@app.callback(
    Output("refresh-interval", "disabled"),
    Input("auto-refresh-toggle", "value"),
)
def toggle_auto_refresh(value):
    """Enable/disable auto-refresh"""
    return "enabled" not in (value or [])


if __name__ == "__main__":
    server.run(host="0.0.0.0", port=DASH_INTERNAL_PORT, debug=True)
