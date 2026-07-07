"""Intentionally broken test file for E2E validation of the CI Triage Agent.

Usage:
  python -m pytest scripts/test_failure_example.py  # this will fail
"""


def calculate_total(quantity: int, price: int) -> int:
    return quantity * price


def test_calculate_total_zero_quantity():
    assert calculate_total(10, 0) == 100
