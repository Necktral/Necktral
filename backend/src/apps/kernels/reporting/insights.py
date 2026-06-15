"""
AI-powered insights and anomaly detection for reporting datasets.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from django.utils import timezone


@dataclass
class AnomalyConfig:
    """Configuration for anomaly detection"""
    sensitivity: float = 2.0  # Standard deviations for z-score
    min_samples: int = 10
    enable_seasonal_detection: bool = True
    window_size: int = 7  # days


class InsightEngine:
    """
    AI-powered insight generation for datasets.

    Features:
    - Anomaly detection using statistical methods
    - Trend analysis
    - Comparative insights
    - Predictive analytics (simple forecasting)
    """

    def __init__(self, config: AnomalyConfig | None = None):
        self.config = config or AnomalyConfig()

    def detect_anomalies(
        self,
        data: list[dict[str, Any]],
        metric_key: str,
        timestamp_key: str = "date",
    ) -> list[dict[str, Any]]:
        """
        Detect anomalies in time-series data using z-score method.

        Args:
            data: Time-series dataset rows
            metric_key: Key of metric to analyze
            timestamp_key: Key of timestamp field

        Returns:
            List of detected anomalies with context
        """
        if len(data) < self.config.min_samples:
            return []

        # Extract values
        values = [float(row.get(metric_key, 0)) for row in data]

        # Calculate statistics
        mean = np.mean(values)
        std = np.std(values)

        if std == 0:
            return []

        # Detect anomalies using z-score
        anomalies = []
        for i, row in enumerate(data):
            value = float(row.get(metric_key, 0))
            z_score = abs((value - mean) / std)

            if z_score > self.config.sensitivity:
                anomalies.append({
                    "index": i,
                    "timestamp": row.get(timestamp_key),
                    "value": value,
                    "expected": round(mean, 2),
                    "deviation": round(z_score, 2),
                    "severity": self._classify_severity(z_score),
                    "type": "statistical_outlier",
                })

        return anomalies

    def detect_trend(
        self,
        data: list[dict[str, Any]],
        metric_key: str,
    ) -> dict[str, Any]:
        """
        Analyze trend direction and strength.

        Args:
            data: Time-series dataset rows
            metric_key: Key of metric to analyze

        Returns:
            Trend analysis with direction and confidence
        """
        if len(data) < 2:
            return {"trend": "insufficient_data"}

        values = [float(row.get(metric_key, 0)) for row in data]

        # Simple linear regression
        x = np.arange(len(values))
        coefficients = np.polyfit(x, values, 1)
        slope = coefficients[0]

        # Determine trend direction
        if abs(slope) < 0.01:
            direction = "stable"
        elif slope > 0:
            direction = "increasing"
        else:
            direction = "decreasing"

        # Calculate R-squared for confidence
        predicted = np.polyval(coefficients, x)
        ss_res = np.sum((values - predicted) ** 2)
        ss_tot = np.sum((values - np.mean(values)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        return {
            "trend": direction,
            "slope": round(float(slope), 4),
            "confidence": round(float(r_squared), 3),
            "start_value": round(float(values[0]), 2),
            "end_value": round(float(values[-1]), 2),
            "change_pct": round(((values[-1] - values[0]) / values[0] * 100) if values[0] != 0 else 0, 2),
        }

    def generate_comparative_insights(
        self,
        current: dict[str, Any],
        previous: dict[str, Any],
        metric_keys: list[str],
    ) -> list[dict[str, Any]]:
        """
        Generate comparative insights between periods.

        Args:
            current: Current period data
            previous: Previous period data
            metric_keys: List of metrics to compare

        Returns:
            List of comparative insights
        """
        insights = []

        for key in metric_keys:
            current_value = float(current.get(key, 0))
            previous_value = float(previous.get(key, 0))

            if previous_value == 0:
                continue

            change_pct = ((current_value - previous_value) / previous_value) * 100

            insights.append({
                "metric": key,
                "current": round(current_value, 2),
                "previous": round(previous_value, 2),
                "change": round(current_value - previous_value, 2),
                "change_pct": round(change_pct, 2),
                "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "stable",
                "significance": self._classify_change_significance(abs(change_pct)),
            })

        return insights

    def forecast_simple(
        self,
        data: list[dict[str, Any]],
        metric_key: str,
        periods: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Simple linear forecast for next periods.

        Args:
            data: Historical time-series data
            metric_key: Key of metric to forecast
            periods: Number of periods to forecast

        Returns:
            Forecasted values
        """
        if len(data) < 2:
            return []

        values = [float(row.get(metric_key, 0)) for row in data]
        x = np.arange(len(values))

        # Fit linear model
        coefficients = np.polyfit(x, values, 1)

        # Generate forecasts
        forecasts = []
        last_index = len(values)

        for i in range(periods):
            forecast_index = last_index + i
            forecast_value = np.polyval(coefficients, forecast_index)

            forecasts.append({
                "period": i + 1,
                "value": round(float(forecast_value), 2),
                "confidence": "low",  # Simple model has low confidence
            })

        return forecasts

    def generate_insights_summary(
        self,
        data: list[dict[str, Any]],
        metric_key: str,
        timestamp_key: str = "date",
    ) -> dict[str, Any]:
        """
        Generate comprehensive insights summary.

        Args:
            data: Dataset rows
            metric_key: Key of metric to analyze
            timestamp_key: Key of timestamp field

        Returns:
            Comprehensive insights
        """
        anomalies = self.detect_anomalies(data, metric_key, timestamp_key)
        trend = self.detect_trend(data, metric_key)
        forecast = self.forecast_simple(data, metric_key, periods=3)

        return {
            "anomalies": anomalies,
            "trend": trend,
            "forecast": forecast,
            "generated_at": timezone.now().isoformat(),
        }

    def _classify_severity(self, z_score: float) -> str:
        """Classify anomaly severity based on z-score"""
        if z_score > 4:
            return "critical"
        elif z_score > 3:
            return "high"
        elif z_score > 2:
            return "medium"
        else:
            return "low"

    def _classify_change_significance(self, change_pct: float) -> str:
        """Classify change significance"""
        if change_pct > 50:
            return "very_high"
        elif change_pct > 25:
            return "high"
        elif change_pct > 10:
            return "medium"
        elif change_pct > 5:
            return "low"
        else:
            return "minimal"


class AlertEngine:
    """
    Alert generation based on insights and thresholds.
    """

    def __init__(self):
        self.alert_rules: list[dict[str, Any]] = []

    def add_rule(
        self,
        rule_id: str,
        dataset_key: str,
        metric_key: str,
        condition: str,
        threshold: float,
        severity: str = "medium",
    ) -> None:
        """
        Add alert rule.

        Args:
            rule_id: Unique rule identifier
            dataset_key: Dataset to monitor
            metric_key: Metric to check
            condition: Condition type ('greater_than', 'less_than', 'equals', 'anomaly')
            threshold: Threshold value
            severity: Alert severity
        """
        self.alert_rules.append({
            "rule_id": rule_id,
            "dataset_key": dataset_key,
            "metric_key": metric_key,
            "condition": condition,
            "threshold": threshold,
            "severity": severity,
            "created_at": timezone.now().isoformat(),
        })

    def evaluate_rules(
        self,
        dataset_key: str,
        data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Evaluate all rules for a dataset.

        Args:
            dataset_key: Dataset identifier
            data: Current dataset result

        Returns:
            List of triggered alerts
        """
        alerts = []

        for rule in self.alert_rules:
            if rule["dataset_key"] != dataset_key:
                continue

            # Extract metric value
            metric_value = data.get(rule["metric_key"])
            if metric_value is None:
                continue

            # Evaluate condition
            triggered = False
            if rule["condition"] == "greater_than":
                triggered = float(metric_value) > rule["threshold"]
            elif rule["condition"] == "less_than":
                triggered = float(metric_value) < rule["threshold"]
            elif rule["condition"] == "equals":
                triggered = float(metric_value) == rule["threshold"]

            if triggered:
                alerts.append({
                    "rule_id": rule["rule_id"],
                    "severity": rule["severity"],
                    "message": f"{rule['metric_key']} {rule['condition']} {rule['threshold']}",
                    "actual_value": float(metric_value),
                    "threshold": rule["threshold"],
                    "timestamp": timezone.now().isoformat(),
                })

        return alerts


# Global instances
_insight_engine: InsightEngine | None = None
_alert_engine: AlertEngine | None = None


def get_insight_engine() -> InsightEngine:
    """Get global insight engine instance"""
    global _insight_engine
    if _insight_engine is None:
        _insight_engine = InsightEngine()
    return _insight_engine


def get_alert_engine() -> AlertEngine:
    """Get global alert engine instance"""
    global _alert_engine
    if _alert_engine is None:
        _alert_engine = AlertEngine()
    return _alert_engine
