from datetime import datetime, timezone

import pytest

from whatsapp_integration import WhatsAppConfiguration, check_budget, check_rate_limit, usage_period_keys

pytestmark = pytest.mark.unit


def configuration(**overrides):
    values = {"daily_message_limit": 10, "monthly_message_limit": 100, "daily_cost_limit": 5.0, "monthly_cost_limit": 25.0, "minimum_send_interval_seconds": 6}
    values.update(overrides)
    return WhatsAppConfiguration(**values)


def test_daily_and_monthly_message_limits_block():
    with pytest.raises(ValueError, match="BUDGET_LIMIT_REACHED"):
        check_budget({"daily_count": 10, "monthly_count": 10, "daily_cost": 0, "monthly_cost": 0}, configuration(), 0)
    with pytest.raises(ValueError, match="BUDGET_LIMIT_REACHED"):
        check_budget({"daily_count": 1, "monthly_count": 100, "daily_cost": 0, "monthly_cost": 0}, configuration(), 0)


def test_daily_and_monthly_cost_limits_block():
    with pytest.raises(ValueError, match="BUDGET_LIMIT_REACHED"):
        check_budget({"daily_count": 1, "monthly_count": 1, "daily_cost": 4.9, "monthly_cost": 5}, configuration(), 0.11)
    with pytest.raises(ValueError, match="BUDGET_LIMIT_REACHED"):
        check_budget({"daily_count": 1, "monthly_count": 1, "daily_cost": 1, "monthly_cost": 24.9}, configuration(), 0.11)


def test_budget_below_limits_passes_and_is_tenant_independent():
    check_budget({"company_id": "a", "daily_count": 9, "monthly_count": 99, "daily_cost": 4.0, "monthly_cost": 20.0}, configuration(), 0.1)
    check_budget({"company_id": "b", "daily_count": 0, "monthly_count": 0, "daily_cost": 0, "monthly_cost": 0}, configuration(), 0.1)


def test_period_keys_reset_by_day_and_month():
    assert usage_period_keys(datetime(2026, 8, 31, 23, 59, tzinfo=timezone.utc)) == ("2026-08-31", "2026-08")
    assert usage_period_keys(datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)) == ("2026-09-01", "2026-09")


def test_conservative_rate_limit_blocks_pair_too_soon():
    now = datetime(2026, 8, 15, 12, 0, 5, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="RATE_LIMIT"):
        check_rate_limit("2026-08-15T12:00:00+00:00", configuration(), now)
    check_rate_limit("2026-08-15T11:59:59+00:00", configuration(), now)
