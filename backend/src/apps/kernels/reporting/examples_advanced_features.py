"""
Example usage scripts for Advanced Reporting & Analytics features.

This file demonstrates how to use the new state-of-the-art features.
"""
from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.kernels.reporting.caching import get_cache_manager
from apps.kernels.reporting.insights import get_alert_engine, get_insight_engine
from apps.kernels.reporting.collaboration_models import (
    DataQualityAlert,
    ReportAnnotation,
    ReportComment,
    ReportShare,
)
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


# ============================================================================
# 1. ADVANCED CACHING EXAMPLES
# ============================================================================

def example_caching_basic():
    """Basic cache usage"""
    cache_mgr = get_cache_manager()

    # Generate cache key
    cache_key = cache_mgr.generate_cache_key(
        dataset_key="accounting.pnl.period",
        filters={"date_from": "2026-01-01", "date_to": "2026-01-31"},
        company_id=1,
        branch_id=10,
    )

    # Try to get from cache
    cached_result = cache_mgr.get(cache_key)

    if cached_result is None:
        print("Cache MISS - executing query")
        # Execute actual dataset query here
        result = {"rows": [...], "run_id": 12345}

        # Store in cache for 5 minutes
        cache_mgr.set(cache_key, result, ttl=300)
    else:
        print("Cache HIT - returning cached data")
        result = cached_result

    return result


def example_caching_metrics():
    """View cache performance metrics"""
    cache_mgr = get_cache_manager()

    metrics = cache_mgr.get_metrics()
    print(f"Cache Statistics:")
    print(f"  Hits: {metrics['hits']}")
    print(f"  Misses: {metrics['misses']}")
    print(f"  Total Requests: {metrics['total_requests']}")
    print(f"  Hit Rate: {metrics['hit_rate_pct']}%")

    # Reset metrics
    cache_mgr.reset_metrics()


def example_cache_warming():
    """Pre-warm cache with common queries"""
    cache_mgr = get_cache_manager()

    # Define common filter combinations
    today = date.today()
    filters_list = [
        {"date_from": str(today), "date_to": str(today)},
        {"date_from": str(today - timedelta(days=7)), "date_to": str(today)},
        {"date_from": str(today - timedelta(days=30)), "date_to": str(today)},
    ]

    def execute_dataset_mock(dataset_key, filters):
        # Mock execution - replace with actual execution
        return {"rows": [], "run_id": 1}

    warmed = cache_mgr.warm_cache(
        dataset_key="fuel.sales.by_pump.daily",
        filters_list=filters_list,
        company_id=1,
        branch_id=10,
        executor_func=execute_dataset_mock,
    )

    print(f"Warmed {warmed} cache entries")


# ============================================================================
# 2. AI INSIGHTS EXAMPLES
# ============================================================================

def example_anomaly_detection():
    """Detect anomalies in sales data"""
    insight_engine = get_insight_engine()

    # Sample dataset (normally from DB)
    sales_data = [
        {"date": "2026-04-01", "total_amount": 85000},
        {"date": "2026-04-02", "total_amount": 82000},
        {"date": "2026-04-03", "total_amount": 88000},
        {"date": "2026-04-04", "total_amount": 86000},
        {"date": "2026-04-05", "total_amount": 150000},  # Anomaly!
        {"date": "2026-04-06", "total_amount": 84000},
        {"date": "2026-04-07", "total_amount": 87000},
    ]

    anomalies = insight_engine.detect_anomalies(
        data=sales_data,
        metric_key="total_amount",
        timestamp_key="date",
    )

    print("Detected Anomalies:")
    for anomaly in anomalies:
        print(f"  {anomaly['timestamp']}: ${anomaly['value']:,.2f}")
        print(f"    Expected: ${anomaly['expected']:,.2f}")
        print(f"    Deviation: {anomaly['deviation']} std devs")
        print(f"    Severity: {anomaly['severity']}")


def example_trend_analysis():
    """Analyze trends in revenue"""
    insight_engine = get_insight_engine()

    revenue_data = [
        {"month": "Jan", "revenue": 100000},
        {"month": "Feb", "revenue": 105000},
        {"month": "Mar", "revenue": 110000},
        {"month": "Apr", "revenue": 115000},
        {"month": "May", "revenue": 120000},
    ]

    trend = insight_engine.detect_trend(
        data=revenue_data,
        metric_key="revenue",
    )

    print(f"Trend Analysis:")
    print(f"  Direction: {trend['trend']}")
    print(f"  Slope: {trend['slope']}")
    print(f"  Confidence: {trend['confidence'] * 100:.1f}%")
    print(f"  Change: {trend['change_pct']}%")


def example_forecasting():
    """Simple forecasting"""
    insight_engine = get_insight_engine()

    historical_data = [
        {"quarter": "Q1", "sales": 250000},
        {"quarter": "Q2", "sales": 270000},
        {"quarter": "Q3", "sales": 290000},
        {"quarter": "Q4", "sales": 310000},
    ]

    forecast = insight_engine.forecast_simple(
        data=historical_data,
        metric_key="sales",
        periods=2,
    )

    print("Sales Forecast:")
    for period in forecast:
        print(f"  Period +{period['period']}: ${period['value']:,.2f} ({period['confidence']} confidence)")


def example_alert_rules():
    """Configure and evaluate alert rules"""
    alert_engine = get_alert_engine()

    # Add alert rules
    alert_engine.add_rule(
        rule_id="low_daily_sales",
        dataset_key="fuel.sales.by_pump.daily",
        metric_key="amount_total",
        condition="less_than",
        threshold=50000,
        severity="high",
    )

    alert_engine.add_rule(
        rule_id="high_expenses",
        dataset_key="accounting.pnl.period",
        metric_key="expenses_total",
        condition="greater_than",
        threshold=200000,
        severity="critical",
    )

    # Evaluate rules
    current_data = {
        "amount_total": 45000,  # Will trigger low_sales alert
        "date": "2026-04-14",
    }

    alerts = alert_engine.evaluate_rules(
        dataset_key="fuel.sales.by_pump.daily",
        data=current_data,
    )

    print(f"Triggered {len(alerts)} alerts:")
    for alert in alerts:
        print(f"  [{alert['severity'].upper()}] {alert['message']}")
        print(f"    Actual: {alert['actual_value']}, Threshold: {alert['threshold']}")


# ============================================================================
# 3. COLLABORATION EXAMPLES
# ============================================================================

def example_create_annotation():
    """Create annotation on report"""
    user = User.objects.get(username="analyst@necktral.com")
    company = OrgUnit.objects.get(code="NECKTRAL", unit_type=OrgUnit.UnitType.COMPANY)

    annotation = ReportAnnotation.objects.create(
        annotation_type=ReportAnnotation.AnnotationType.INSIGHT,
        company=company,
        dataset_key="accounting.pnl.period",
        run_id=12345,
        target_path={
            "chart": "main_pnl",
            "point": {"account_code": "6100"},
        },
        title="Marketing expenses spike",
        content="Marketing department exceeded budget by 45% in Q1. Requires investigation.",
        metadata={"color": "#f59e0b", "priority": "high"},
        created_by=user,
        is_shared=True,
    )

    print(f"Created annotation: {annotation.id}")
    return annotation


def example_add_comments():
    """Add threaded comments to annotation"""
    annotation = ReportAnnotation.objects.get(id=1)
    manager = User.objects.get(username="manager@necktral.com")
    cfo = User.objects.get(username="cfo@necktral.com")

    # Manager comments
    comment1 = ReportComment.objects.create(
        annotation=annotation,
        content="I reviewed this with the marketing team. The spike is due to Q1 campaign.",
        created_by=manager,
    )

    # CFO replies
    comment2 = ReportComment.objects.create(
        annotation=annotation,
        parent_comment=comment1,
        content="Thanks for clarifying. Please ensure this is documented in variance analysis.",
        created_by=cfo,
    )

    print(f"Added {2} comments")


def example_share_report():
    """Share report with specific permissions"""
    user = User.objects.get(username="analyst@necktral.com")
    stakeholder = User.objects.get(username="board.member@necktral.com")
    company = OrgUnit.objects.get(code="NECKTRAL", unit_type=OrgUnit.UnitType.COMPANY)

    share = ReportShare.objects.create(
        company=company,
        workspace_key="executive",
        share_type=ReportShare.ShareType.VIEW_ONLY,
        shared_with_user=stakeholder,
        shared_by=user,
        expires_at=timezone.now() + timedelta(days=7),
    )

    print(f"Shared workspace 'executive' with {stakeholder.email}")
    print(f"  Permission: {share.share_type}")
    print(f"  Expires: {share.expires_at}")

    return share


def example_quality_alert():
    """Create data quality alert"""
    company = OrgUnit.objects.get(code="NECKTRAL", unit_type=OrgUnit.UnitType.COMPANY)
    branch = OrgUnit.objects.get(code="BRANCH_01", unit_type=OrgUnit.UnitType.BRANCH)

    alert = DataQualityAlert.objects.create(
        alert_code="DQ_MISSING_PUMP_DATA",
        company=company,
        branch=branch,
        dataset_key="fuel.sales.by_pump.daily",
        run_id=67890,
        severity=DataQualityAlert.Severity.WARNING,
        title="Missing sales data for Pump #3",
        description="No sales recorded for pump #3 in the last 4 hours",
        details={
            "pump_id": 3,
            "last_sale_timestamp": "2026-04-14T10:30:00Z",
            "gap_hours": 4,
            "expected_sales_per_hour": 15,
        },
        detection_rule="pump_activity_monitor",
    )

    print(f"Created quality alert: {alert.id}")
    print(f"  Severity: {alert.severity}")
    print(f"  Status: {alert.status}")

    return alert


def example_acknowledge_alert():
    """Acknowledge a quality alert"""
    alert = DataQualityAlert.objects.get(id=1)
    ops_manager = User.objects.get(username="ops.manager@necktral.com")

    alert.acknowledge(user=ops_manager)

    print(f"Alert {alert.id} acknowledged by {ops_manager.get_full_name()}")


def example_resolve_annotation():
    """Resolve an annotation after addressing the issue"""
    annotation = ReportAnnotation.objects.get(id=1)
    cfo = User.objects.get(username="cfo@necktral.com")

    annotation.resolve(user=cfo)

    print(f"Annotation {annotation.id} resolved by {cfo.get_full_name()}")


# ============================================================================
# 4. EXPORT EXAMPLES
# ============================================================================

def example_excel_export():
    """Export dataset to Excel with formatting"""
    from apps.kernels.reporting.advanced_exports import export_dataset_to_excel
    from apps.kernels.reporting.registry import get_dataset_spec

    # Get dataset result (mock)
    dataset_result = {
        "rows": [
            {"account_code": "1000", "account_name": "Cash", "balance": 50000},
            {"account_code": "1100", "account_name": "Accounts Receivable", "balance": 75000},
            {"account_code": "2000", "account_name": "Accounts Payable", "balance": -30000},
        ],
        "run_id": 12345,
    }

    dataset_spec = get_dataset_spec("accounting.trial_balance.period")

    response = export_dataset_to_excel(
        dataset_result=dataset_result,
        dataset_spec=dataset_spec,
        filename="trial_balance_april_2026.xlsx",
    )

    print(f"Excel export ready: {response['Content-Disposition']}")
    return response


def example_pdf_export():
    """Export dataset to PDF with professional formatting"""
    from apps.kernels.reporting.advanced_exports import export_dataset_to_pdf
    from apps.kernels.reporting.registry import get_dataset_spec

    dataset_result = {
        "rows": [
            {"account_code": "4000", "account_name": "Revenue", "balance": 500000},
            {"account_code": "5000", "account_name": "Cost of Sales", "balance": -200000},
            {"account_code": "6000", "account_name": "Operating Expenses", "balance": -150000},
        ],
        "run_id": 12346,
    }

    dataset_spec = get_dataset_spec("accounting.pnl.period")

    response = export_dataset_to_pdf(
        dataset_result=dataset_result,
        dataset_spec=dataset_spec,
        filename="pnl_q1_2026.pdf",
        title="Profit & Loss Statement - Q1 2026",
    )

    print(f"PDF export ready: {response['Content-Disposition']}")
    return response


# ============================================================================
# MAIN DEMO
# ============================================================================

def run_all_examples():
    """Run all example functions"""
    print("=" * 70)
    print("ADVANCED REPORTING & ANALYTICS - EXAMPLES")
    print("=" * 70)

    print("\n1. CACHING")
    print("-" * 70)
    example_caching_basic()
    example_caching_metrics()
    # example_cache_warming()

    print("\n2. AI INSIGHTS")
    print("-" * 70)
    example_anomaly_detection()
    example_trend_analysis()
    example_forecasting()
    example_alert_rules()

    print("\n3. COLLABORATION")
    print("-" * 70)
    # example_create_annotation()
    # example_add_comments()
    # example_share_report()
    # example_quality_alert()
    # example_acknowledge_alert()
    # example_resolve_annotation()

    print("\n4. EXPORTS")
    print("-" * 70)
    # example_excel_export()
    # example_pdf_export()

    print("\n" + "=" * 70)
    print("All examples completed!")
    print("=" * 70)


if __name__ == "__main__":
    # Uncomment the examples you want to run
    example_anomaly_detection()
    example_trend_analysis()
    # run_all_examples()
