## Deferred Notes

- The extracted benchmark paper description does not fully match the shipped reference repo code: loss, augmentation, batch-size, and checkpoint-selection details appear to differ and should be reconciled before treating the paper numbers as a strict reproduction target.
- The local training workflow loads the test split but only reports validation metrics; add a dedicated local test evaluation entrypoint so benchmark comparisons do not rely on validation logs.
- The current random validation split appears harder and more heterogeneous than the official test split based on lesion-coverage statistics, so validation F1 is likely pessimistic relative to held-out test performance.