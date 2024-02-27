# Modified from OpenAI's diffusion repos
#     GLIDE: https://github.com/openai/glide-text2im/blob/main/glide_text2im/gaussian_diffusion.py
#     ADM:   https://github.com/openai/guided-diffusion/blob/main/guided_diffusion
#     IDDPM: https://github.com/openai/improved-diffusion/blob/main/improved_diffusion/gaussian_diffusion.py

import torch as th
import numpy as np


def normal_kl(mean1, logvar1, mean2, logvar2):
    """    Compute the KL divergence between two Gaussian distributions.

    This function computes the Kullback-Leibler (KL) divergence between two Gaussian distributions. The shapes of the input parameters are automatically broadcasted, allowing for comparisons between batches and scalars.

    Args:
        mean1 (Tensor or float): The mean of the first Gaussian distribution.
        logvar1 (Tensor or float): The log variance of the first Gaussian distribution.
        mean2 (Tensor or float): The mean of the second Gaussian distribution.
        logvar2 (Tensor or float): The log variance of the second Gaussian distribution.

    Returns:
        Tensor: The computed KL divergence between the two Gaussian distributions.

    Raises:
        AssertionError: If all input arguments are not Tensors.
    """
    tensor = None
    for obj in (mean1, logvar1, mean2, logvar2):
        if isinstance(obj, th.Tensor):
            tensor = obj
            break
    assert tensor is not None, "at least one argument must be a Tensor"

    # Force variances to be Tensors. Broadcasting helps convert scalars to
    # Tensors, but it does not work for th.exp().
    logvar1, logvar2 = [
        x if isinstance(x, th.Tensor) else th.tensor(x).to(tensor)
        for x in (logvar1, logvar2)
    ]

    return 0.5 * (
        -1.0
        + logvar2
        - logvar1
        + th.exp(logvar1 - logvar2)
        + ((mean1 - mean2) ** 2) * th.exp(-logvar2)
    )


def approx_standard_normal_cdf(x):
    """    A fast approximation of the cumulative distribution function of the standard normal.

    Args:
        x (float): The input value for the standard normal distribution.

    Returns:
        float: The approximate cumulative distribution function value.
    """
    return 0.5 * (1.0 + th.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * th.pow(x, 3))))


def continuous_gaussian_log_likelihood(x, *, means, log_scales):
    """    Compute the log-likelihood of a continuous Gaussian distribution.

    Args:
        x (tensor): The targets.
        means (tensor): The Gaussian mean Tensor.
        log_scales (tensor): The Gaussian log stddev Tensor.

    Returns:
        tensor: A tensor like x of log probabilities (in nats).
    """
    centered_x = x - means
    inv_stdv = th.exp(-log_scales)
    normalized_x = centered_x * inv_stdv
    log_probs = th.distributions.Normal(th.zeros_like(x), th.ones_like(x)).log_prob(normalized_x)
    return log_probs


def discretized_gaussian_log_likelihood(x, *, means, log_scales):
    """    Compute the log-likelihood of a Gaussian distribution discretizing to a
    given image.

    Args:
        x (Tensor): The target images. It is assumed that this was uint8 values,
            rescaled to the range [-1, 1].
        means (Tensor): The Gaussian mean Tensor.
        log_scales (Tensor): The Gaussian log stddev Tensor.

    Returns:
        Tensor: A tensor like x of log probabilities (in nats).
    """
    assert x.shape == means.shape == log_scales.shape
    centered_x = x - means
    inv_stdv = th.exp(-log_scales)
    plus_in = inv_stdv * (centered_x + 1.0 / 255.0)
    cdf_plus = approx_standard_normal_cdf(plus_in)
    min_in = inv_stdv * (centered_x - 1.0 / 255.0)
    cdf_min = approx_standard_normal_cdf(min_in)
    log_cdf_plus = th.log(cdf_plus.clamp(min=1e-12))
    log_one_minus_cdf_min = th.log((1.0 - cdf_min).clamp(min=1e-12))
    cdf_delta = cdf_plus - cdf_min
    log_probs = th.where(
        x < -0.999,
        log_cdf_plus,
        th.where(x > 0.999, log_one_minus_cdf_min, th.log(cdf_delta.clamp(min=1e-12))),
    )
    assert log_probs.shape == x.shape
    return log_probs
