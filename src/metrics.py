import numpy as np
from scipy.spatial.distance import directed_hausdorff
from sklearn.metrics import accuracy_score


def precision(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    intersection = (y_true * y_pred).sum()
    return float((intersection + 1e-15) / (y_pred.sum() + 1e-15))


def recall(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    intersection = (y_true * y_pred).sum()
    return float((intersection + 1e-15) / (y_true.sum() + 1e-15))


def F2(y_true: np.ndarray, y_pred: np.ndarray, beta: float = 2.0) -> float:
    p = precision(y_true, y_pred)
    r = recall(y_true, y_pred)
    return float((1 + beta**2.0) * (p * r) / (beta**2 * p + r + 1e-15))


def dice_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(
        (2 * (y_true * y_pred).sum() + 1e-15)
        / (y_true.sum() + y_pred.sum() + 1e-15)
    )


def jac_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    intersection = (y_true * y_pred).sum()
    union = y_true.sum() + y_pred.sum() - intersection
    return float((intersection + 1e-15) / (union + 1e-15))


def hd_dist(preds: np.ndarray, targets: np.ndarray) -> float:
    return float(directed_hausdorff(preds, targets)[0])


def calculate_metrics(
    y_true: "torch.Tensor", y_pred: "torch.Tensor"
) -> list[float]:
    """Compute all metrics from raw tensors. Returns [jac, f1, recall, precision, acc, f2, hd]."""
    import torch  # deferred to avoid circular import at module level

    y_true_np = y_true.detach().cpu().numpy()
    y_pred_np = y_pred.detach().cpu().numpy()

    y_pred_np = (y_pred_np > 0.5).astype(np.uint8)
    y_true_np = (y_true_np > 0.5).astype(np.uint8)

    # Hausdorff distance — operates on 2D spatial arrays.
    if len(y_true_np.shape) == 3:
        score_hd = hd_dist(y_true_np[0], y_pred_np[0])
    elif len(y_true_np.shape) == 4:
        score_hd = hd_dist(y_true_np[0, 0], y_pred_np[0, 0])
    else:
        score_hd = 0.0

    # Flatten for pixel-level metrics.
    y_pred_flat = y_pred_np.reshape(-1)
    y_true_flat = y_true_np.reshape(-1)

    score_jaccard = jac_score(y_true_flat, y_pred_flat)
    score_f1 = dice_score(y_true_flat, y_pred_flat)
    score_recall = recall(y_true_flat, y_pred_flat)
    score_precision = precision(y_true_flat, y_pred_flat)
    score_fbeta = F2(y_true_flat, y_pred_flat)
    score_acc = float(accuracy_score(y_true_flat, y_pred_flat))

    return [
        score_jaccard,
        score_f1,
        score_recall,
        score_precision,
        score_acc,
        score_fbeta,
        score_hd,
    ]
