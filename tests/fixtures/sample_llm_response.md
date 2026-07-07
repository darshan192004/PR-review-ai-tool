## Root Cause
The test `test_calc` in `tests/test_app.py` is asserting that `calculate_total(10, 0)` returns 100, but the function returns 0. This suggests that `calculate_total` does not handle zero quantities correctly — likely a division by zero or an unhandled edge case where the quantity is zero results in a zero total instead of applying the unit price calculation.

## Affected File
`src/app.py:25` (the `calculate_total` function)

## Code Patch
```diff
 def calculate_total(quantity: int, price: int) -> int:
+    if quantity <= 0:
+        return 0
     return quantity * price
```

## Suggested Fix Description
Add a guard clause to return 0 when quantity is zero or negative, preventing downstream errors when the caller passes zero inventory items. This makes the function robust against edge case inputs while preserving the core quantity × price logic.
