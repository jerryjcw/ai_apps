"""
Deliveroo Machine Learning Pipeline - Model Evaluation Module
Evaluate the performance of a given model.
"""
from logging import getLogger

logger = getLogger(__name__)

import math
from pipeline_utils.config import MODEL_PERF_THRESHOLD

def evaluate_model(y_test: list[int], y_pred: list[float]) -> float:
    """
    Compute log-loss given prediction y_pred and ground truth y_test. 
    Return the AVERAGE log-loss of the whole dataset, if it exceeds the MODEL_PERF_THRESHOLD, raise an error to fail the model evaluation.
    Assumption: We clip the probablity instead of considering out-of-bound values as errors.

    Args:
        y_test: Ground truth labels (list of integers, 0 or 1).
        y_pred: Predicted probabilities (list of floats, range [0, 1]).

    Returns:
        float: The calculated average log-loss.

    Raises:
        ValueError: If data consistency checks fail.
        RuntimeError: If the calculated log-loss exceeds MODEL_PERF_THRESHOLD.
    """
    
    # 1. Input Validation & Guard Rails, raise value error if input is invalid
    if not isinstance(y_test, list) or not isinstance(y_pred, list):
        raise ValueError("Inputs must be lists.")
    if len(y_test) != len(y_pred) or len(y_test) == 0:
        raise ValueError("Input lists must be of the same non-zero length.")
    
    n = len(y_test)

    eps = 1e-15    
    total_log_loss = 0.0
    
    # Compute the loss for the datset (average).
    for y_true, y_prob in zip(y_test, y_pred):
        # Clip probability [0, 1]
        p = max(eps, y_prob)
        p = min(1 - eps, p)
        
        # BCE
        if y_true == 1:
            total_log_loss -= math.log(p)
        elif y_true == 0:
            total_log_loss -= math.log(1 - p)
        else:
            raise ValueError(f"Invalid label detected: {y_true} in data pair ({y_true}, {y_prob}). Expected 0 or 1.")

    avg_log_loss = total_log_loss / n

    # Apply threshold check
    if avg_log_loss > MODEL_PERF_THRESHOLD:
        # In a production pipeline, this error should trigger an alert or stop the deployment
        raise RuntimeError(
            f"Model performance failed validation, log-loss {avg_log_loss:.6f} exceeds threshold {MODEL_PERF_THRESHOLD}."
        )

    logger.info(f"Evaluation successful. Log-loss: {avg_log_loss:.6f}")
    return avg_log_loss