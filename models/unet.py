"""Plain U-Net baseline from ``segmentation_models_pytorch``.

Brief, Section 7.5: "Plain U-Net from ``segmentation-models-pytorch`` as the
baseline." This module provides it, built from the configured channel stack
and class list so it cannot disagree with the data it is trained on.

**There are two baselines in this project, and they answer different
questions.**

``models.attention_unet.plain_unet`` is the *controlled* ablation: the same
class as the Attention U-Net with the gates removed, so it has identical
depth, widths, normalisation and upsampling. Comparing against it isolates the
contribution of the attention gates, which is what Section 7.5's required
comparison is about.

This module is the *external* baseline. An ``smp`` U-Net differs from our
Attention U-Net in encoder architecture, normalisation, initialisation and
decoder details all at once, so a difference in score cannot be attributed to
the gates. What it does answer is whether our implementation is competitive
with a standard one at all — which is worth knowing, and is why the brief
names it.

Both should be reported. Reporting only the external baseline would let an
implementation artefact masquerade as an attention result; reporting only the
ablation would leave the whole architecture unvalidated.

Encoder weights: ImageNet weights expect three RGB channels. Against this
project's fifteen-channel stack ``smp`` adapts the first convolution rather
than refusing, so the transfer is partial and its benefit is unquantified
here. ``models.baseline_encoder_weights`` defaults to ``null`` (random
initialisation) so that the default run makes no unexamined claim; if weights
are enabled, say so when reporting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    import torch.nn as nn

    from config.schema import Config

log = get_logger(__name__)


class BaselineUNetError(RuntimeError):
    """The baseline could not be constructed as configured."""


def _require_smp() -> Any:
    try:
        import segmentation_models_pytorch as smp
    except ImportError as exc:  # pragma: no cover - environment problem
        raise BaselineUNetError(
            "segmentation_models_pytorch is not installed; add it with "
            "`pip install segmentation-models-pytorch` inside the conda "
            "environment, or use models.attention_unet.plain_unet, which has "
            "no extra dependency and is the controlled ablation"
        ) from exc
    return smp


def baseline_unet(
    cfg: "Config",
    *,
    in_channels: int | None = None,
    num_classes: int | None = None,
) -> "nn.Module":
    """The ``smp`` U-Net sized from config.

    Args:
        in_channels: defaults to ``len(cfg.models.channels)``. Passing a value
            that disagrees with the configured stack is allowed but logged,
            because it is usually a mistake that surfaces much later as a
            shape error in the middle of training.
        num_classes: defaults to ``len(cfg.models.classes)``.

    Returns:
        An ``smp.Unet``.

    Raises:
        BaselineUNetError: if ``segmentation_models_pytorch`` is unavailable or
            the encoder name is not recognised.
    """
    smp = _require_smp()
    settings = cfg.models

    channels = settings.in_channels if in_channels is None else int(in_channels)
    classes = settings.num_classes if num_classes is None else int(num_classes)

    if in_channels is not None and in_channels != settings.in_channels:
        log.warning(
            "baseline built with in_channels=%d but the configured channel "
            "stack has %d entries; the model will not accept patches built "
            "from this config",
            in_channels,
            settings.in_channels,
        )
    if num_classes is not None and num_classes != settings.num_classes:
        log.warning(
            "baseline built with num_classes=%d but %d classes are configured",
            num_classes,
            settings.num_classes,
        )

    try:
        model = smp.Unet(
            encoder_name=settings.baseline_encoder,
            encoder_weights=settings.baseline_encoder_weights,
            in_channels=channels,
            classes=classes,
        )
    except (KeyError, ValueError) as exc:
        raise BaselineUNetError(
            f"segmentation_models_pytorch rejected encoder "
            f"{settings.baseline_encoder!r}: {exc}. See smp's encoder list; "
            f"the name is models.baseline_encoder in config."
        ) from exc

    log.info(
        "baseline U-Net: encoder %s, weights %s, %d input channel(s), "
        "%d class(es)",
        settings.baseline_encoder,
        settings.baseline_encoder_weights or "random init",
        channels,
        classes,
    )
    return model


def parameter_count(model: "nn.Module") -> int:
    """Trainable parameters, for the comparison table."""
    return int(sum(p.numel() for p in model.parameters() if p.requires_grad))
