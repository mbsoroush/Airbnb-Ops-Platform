# Experiment tracking: airbnb_high_demand_proxy

- Dataset: `v1` (`listing_availability_features_v1.parquet`, sha256 `4f6ad33012b6`), cutoff 2026-12-24
- Git commit: `bf1d9fc342de` (dirty: true)
- Tracking: http://localhost:5001
- Split: stratified, test_size 0.2, random_state 42; 5966 train / 1492 test rows, positive rate 0.5748 / 0.5751
- Cross-validation: 5 stratified folds on the training part

## Comparison

Bare metrics (`accuracy` ... `roc_auc`) are computed once on the held-out test part, as is conventional. `cv_*` metrics are out-of-fold on the training part and are the only ones used for selection.

| run_name | leakage_status | model_family | evaluation | threshold | accuracy | precision | recall | f1 | roc_auc | cv_f1 | cv_roc_auc | run_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v0_leaky_logistic_regression | leaky | logistic_regression | random_split | 0.5 | 0.998 | 0.9965 | 1.0 | 0.9983 | 1.0 | 0.9971 | 1.0 | 045d6b59b1e44dbca6a14891a611be98 |
| v1_dummy_baseline | clean | dummy | random_split | 0.5 | 0.5751 | 0.5751 | 1.0 | 0.7302 | 0.5 | 0.73 | 0.5 | c05edad90e8d473ba71c22a4931134fa |
| v2_clean_logistic_regression | clean | logistic_regression | random_split | 0.5 | 0.817 | 0.8563 | 0.8193 | 0.8374 | 0.9003 | 0.847 | 0.9042 | 91f951b8e6164454b14c2f7078be7bdb |
| v3_balanced_logistic_regression | clean | logistic_regression | random_split | 0.5 | 0.8184 | 0.8748 | 0.7984 | 0.8349 | 0.9001 | 0.8433 | 0.9037 | 3da1039ca2fa4dce9fc0e3eeee1792b6 |
| v4_threshold_0.30 | clean | logistic_regression | random_split | 0.3 | 0.8097 | 0.8189 | 0.859 | 0.8385 | 0.9001 | 0.8505 | 0.9037 | b152bfe3ab49481893f13b3bca8401b2 |
| v4_threshold_0.40 | clean | logistic_regression | random_split | 0.4 | 0.819 | 0.8534 | 0.8275 | 0.8402 | 0.9001 | 0.8491 | 0.9037 | e31ae7626f7b4df382cde0aae5389092 |
| v4_threshold_0.60 | clean | logistic_regression | random_split | 0.6 | 0.8123 | 0.8948 | 0.7634 | 0.8239 | 0.9001 | 0.8306 | 0.9037 | 4468bbf632df4ebaa883f3eaac1b7be9 |
| v5_random_forest | clean | random_forest | random_split | 0.5 | 0.8338 | 0.8961 | 0.8042 | 0.8477 | 0.9149 | 0.8573 | 0.9212 | 72d067b78ad94d3096276f59f37e5e95 |
| v5b_random_forest_shallow | clean | random_forest | random_split | 0.5 | 0.8217 | 0.9 | 0.7762 | 0.8335 | 0.9094 | 0.8482 | 0.9169 | eedef69e6e2b4a1fbcf420e8706f8b53 |

## Selected run

- `v5_random_forest` (run id `72d067b78ad94d3096276f59f37e5e95`), tagged `selected_for_serving=true` and `production_candidate=true`
- Rule: Among clean, standard-split runs that are not the dummy baseline, keep those whose cross-validated ROC AUC beats the dummy's by at least 0.05, and take the highest cross-validated ROC AUC. Runs within 0.001 of the best count as tied (for example the same model at different decision thresholds); ties go to the higher cross-validated F1, then to the name. ROC AUC comes first because the positive class is the majority: a dummy that always predicts it already scores a high F1, so F1 alone cannot show skill. The leaky run can never be selected, and test metrics are not used.
- Eligible runs: `v2_clean_logistic_regression`, `v3_balanced_logistic_regression`, `v4_threshold_0.30`, `v4_threshold_0.40`, `v4_threshold_0.60`, `v5_random_forest`, `v5b_random_forest_shallow`

## Final explanation

I selected `v5_random_forest` (run `72d067b78ad94d3096276f59f37e5e95`): its cross-validated ROC AUC is 0.921 and F1 0.857, against 0.500 and 0.730 for the dummy baseline, and its single held-out test result is ROC AUC 0.915, F1 0.848. It was chosen on cross-validated metrics of the training part only, uses clean features, and logs the full preprocessing pipeline. The leaky run `v0_leaky_logistic_regression` reaches ROC AUC 1.000 on the test part because future_available_rate_30d is the quantity the label is made from, so it is rejected whatever its score. Because about 58% of listings are positive, even the dummy gets F1 0.730, which is why selection ranks by ROC AUC first and uses F1 only to break ties between thresholds of the same model. Next I would test on a true temporal split built from several calendar snapshots and add features that are known before the cutoff.

## Decisions

- `instant_bookable` and any other constant column: excluded from the model (instant_bookable). In the Munich file `instant_bookable` is empty, so after the fill rule it is constant False and carries no information. The request contract still contains it.
- Price: `log1p` plus median imputation with a missing indicator, inside the Pipeline, so serving applies the identical transformation (about a third of prices are missing and the maximum is about 80,000 per night).
- `days_since_last_review`: kept because the column contract is fixed. Univariate ROC AUC on the training part (0.5 = no signal): `days_since_last_review` 0.660, `available_rate_last_30d` 0.865, `available_rate_last_90d` 0.878, `total_reviews_before_cutoff` 0.527, `listing_price` 0.527, `accommodates` 0.510.

## Extra comparisons for the selected configuration

These are diagnostics, not part of the selection. Grouped splits hold out whole hosts or neighbourhoods, so they show how much a random split flatters the score. The group labels stay in memory and are never logged. A cross-version check is not independent evidence: both dataset versions contain the same listings.

| run_name | leakage_status | model_family | evaluation | threshold | accuracy | precision | recall | f1 | roc_auc | run_id |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v6_host_grouped_v5_random_forest | clean | random_forest | host_grouped | 0.5 | 0.8366 | 0.8981 | 0.8092 | 0.8513 | 0.9183 | e3b67bab19154df88a57ceb839153dc8 |
| v6_neighbourhood_grouped_v5_random_forest | clean | random_forest | neighbourhood_grouped | 0.5 | 0.8255 | 0.894 | 0.7569 | 0.8198 | 0.9053 | 6bf8b040ec294e809fdbc9c0d2722c22 |
| v6_cross_version_v2_v5_random_forest | clean | random_forest | cross_version_v2 | 0.5 | 0.9669 | 0.967 | 0.9746 | 0.9708 | 0.9872 | d4830af7322849b29050f9a79ae0207f |

## How to read these scores

- The label is a low-availability proxy (booked or blocked by the host), not confirmed demand.
- Features and label come from the same forward-looking calendar snapshot, so none of these numbers prove that the model predicts real bookings, and no split here is a true temporal split.
- The positive class is the majority, so accuracy and F1 of a trivial model are high; compare ROC AUC and the dummy baseline.
