"""Attention U-Net, after Oktay et al. (2018).

Brief, Section 7.5 names this as a required deliverable alongside a plain
U-Net baseline, and makes **the comparison between the two a required
result**.

The attention gate
------------------
A plain U-Net concatenates each encoder skip connection straight into the
decoder. The skip carries high-resolution detail, but it carries *all* of it:
every texture the encoder saw at that scale, relevant or not. In this
project's imagery that includes a great deal of steep, bright, high-frequency
terrain which has nothing to do with water.

An attention gate (Oktay et al. 2018, §3.2) inserts a learned, spatially
varying filter on that skip. It takes the decoder's coarser *gating signal* g
-- which has seen more context -- and the skip x, and produces a coefficient
alpha in (0, 1) per pixel:

    q = psi( relu( W_g g + W_x x ) )
    alpha = sigmoid(q)
    x_hat = alpha * x

So the decoder asks "given what I understand at this coarser scale, which
parts of the fine detail matter?" and suppresses the rest. The gate is
additive rather than multiplicative, which is the paper's choice and is
reported there to perform better despite costing more.

Why this architecture suits this problem
----------------------------------------
Water and terrain shadow are locally near-identical -- both dark, both smooth
-- and are separated mainly by *context*: where in the valley they sit,
whether the surroundings are steep, how the shape relates to the channel.
That is precisely what a gating signal from a coarser scale carries. Whether
it helps here is an empirical question this project is required to answer,
not an assumption; see ``models/evaluate.compare``.

Implementation notes
--------------------
* The channel count is configurable, because the input is a configurable
  channel stack (Section 7.5), not three-band RGB.
* ``bilinear`` upsampling is offered as an alternative to transposed
  convolution: transposed convolutions produce checkerboard artefacts that, on
  a thin lake shoreline, are not cosmetic.
* The gates' attention coefficients can be returned, so that what the model
  attends to can be inspected rather than taken on trust.

Reference
---------
Oktay, O., Schlemper, J., Le Folgoc, L., Lee, M., Heinrich, M., Misawa, K.,
    Mori, K., McDonagh, S., Hammerla, N. Y., Kainz, B., Glocker, B. &
    Rueckert, D. (2018). "Attention U-Net: Learning Where to Look for the
    Pancreas." *MIDL 2018*. arXiv:1804.03999
"""

from __future__ import annotations

from typing import Sequence

import torch
import torch.nn as nn
import torch.nn.functional as F


class DoubleConv(nn.Module):
    """(conv -> BN -> ReLU) x 2, the standard U-Net block."""

    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class AttentionGate(nn.Module):
    """Additive attention gate (Oktay et al. 2018, eq. 1-2).

    Args:
        gate_channels: channels of the gating signal ``g`` from the decoder.
        skip_channels: channels of the encoder skip ``x`` being filtered.
        inter_channels: channels of the intermediate space. The paper uses
            half the skip channels; that is the default here.

    The returned coefficients are per-pixel and single-channel, so the same
    spatial decision is applied across every feature of the skip.
    """

    def __init__(
        self,
        gate_channels: int,
        skip_channels: int,
        inter_channels: int | None = None,
    ) -> None:
        super().__init__()
        inter_channels = inter_channels or max(1, skip_channels // 2)

        self.theta_x = nn.Conv2d(skip_channels, inter_channels, 1, bias=False)
        self.phi_g = nn.Conv2d(gate_channels, inter_channels, 1, bias=True)
        self.psi = nn.Conv2d(inter_channels, 1, 1, bias=True)
        self.norm = nn.BatchNorm2d(skip_channels)

    def forward(
        self, skip: torch.Tensor, gate: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Returns ``(filtered_skip, attention_coefficients)``."""
        theta = self.theta_x(skip)
        phi = self.phi_g(gate)
        if phi.shape[-2:] != theta.shape[-2:]:
            # The gating signal is coarser; bring it up to the skip's grid.
            phi = F.interpolate(
                phi, size=theta.shape[-2:], mode="bilinear", align_corners=False
            )

        alpha = torch.sigmoid(self.psi(F.relu(theta + phi, inplace=True)))
        return self.norm(skip * alpha), alpha


class Up(nn.Module):
    """One decoder step: upsample, gate the skip, concatenate, convolve."""

    def __init__(
        self,
        in_channels: int,
        skip_channels: int,
        out_channels: int,
        *,
        bilinear: bool = True,
        attention: bool = True,
    ) -> None:
        super().__init__()
        if bilinear:
            self.up: nn.Module = nn.Upsample(
                scale_factor=2, mode="bilinear", align_corners=False
            )
            upsampled_channels = in_channels
        else:
            self.up = nn.ConvTranspose2d(in_channels, in_channels // 2, 2, stride=2)
            upsampled_channels = in_channels // 2

        self.gate = (
            AttentionGate(upsampled_channels, skip_channels) if attention else None
        )
        self.conv = DoubleConv(upsampled_channels + skip_channels, out_channels)

    def forward(
        self, x: torch.Tensor, skip: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor | None]:
        x = self.up(x)

        # Odd input sizes leave the upsampled tensor a pixel short.
        if x.shape[-2:] != skip.shape[-2:]:
            x = F.pad(
                x,
                [
                    0,
                    skip.shape[-1] - x.shape[-1],
                    0,
                    skip.shape[-2] - x.shape[-2],
                ],
            )

        alpha = None
        if self.gate is not None:
            skip, alpha = self.gate(skip, x)
        return self.conv(torch.cat([skip, x], dim=1)), alpha


class AttentionUNet(nn.Module):
    """U-Net with attention gates on every skip connection.

    Args:
        in_channels: size of the configured channel stack (Section 7.5), not
            assumed to be 3.
        num_classes: 5 by default -- land, water, landslide/debris, terrain
            shadow, snow/ice.
        features: encoder widths, one per downsampling step.
        bilinear: upsample bilinearly rather than with a transposed
            convolution, avoiding checkerboard artefacts on thin shorelines.
        attention: ``False`` yields an otherwise identical plain U-Net, which
            is what makes the required comparison a controlled one -- the two
            models then differ *only* in the gates.
    """

    def __init__(
        self,
        in_channels: int = 16,
        num_classes: int = 5,
        features: Sequence[int] = (32, 64, 128, 256),
        *,
        bilinear: bool = True,
        attention: bool = True,
    ) -> None:
        super().__init__()
        if in_channels < 1:
            raise ValueError(f"in_channels must be positive, got {in_channels}")
        if num_classes < 2:
            raise ValueError(
                f"num_classes must be at least 2, got {num_classes}"
            )
        if len(features) < 1:
            raise ValueError("features must list at least one encoder width")

        self.in_channels = in_channels
        self.num_classes = num_classes
        self.features = list(features)
        self.attention = attention

        self.inc = DoubleConv(in_channels, features[0])

        self.downs = nn.ModuleList()
        for previous, current in zip(features, features[1:]):
            self.downs.append(
                nn.Sequential(nn.MaxPool2d(2), DoubleConv(previous, current))
            )

        self.bottleneck = nn.Sequential(
            nn.MaxPool2d(2), DoubleConv(features[-1], features[-1] * 2)
        )

        self.ups = nn.ModuleList()
        decoder_in = features[-1] * 2
        for skip_channels in reversed(features):
            self.ups.append(
                Up(
                    decoder_in,
                    skip_channels,
                    skip_channels,
                    bilinear=bilinear,
                    attention=attention,
                )
            )
            decoder_in = skip_channels

        self.outc = nn.Conv2d(features[0], num_classes, 1)

    @property
    def depth(self) -> int:
        return len(self.features)

    def forward(
        self, x: torch.Tensor, *, return_attention: bool = False
    ) -> torch.Tensor | tuple[torch.Tensor, list[torch.Tensor]]:
        """Logits of shape ``(N, num_classes, H, W)``.

        Args:
            return_attention: also return each gate's coefficients, so what
                the model attends to can be inspected rather than assumed.
        """
        if x.dim() != 4:
            raise ValueError(f"expected (N, C, H, W), got shape {tuple(x.shape)}")
        if x.shape[1] != self.in_channels:
            raise ValueError(
                f"model built for {self.in_channels} channel(s) but got "
                f"{x.shape[1]}"
            )

        skips = [self.inc(x)]
        for down in self.downs:
            skips.append(down(skips[-1]))

        out = self.bottleneck(skips[-1])

        coefficients: list[torch.Tensor] = []
        for up, skip in zip(self.ups, reversed(skips)):
            out, alpha = up(out, skip)
            if alpha is not None:
                coefficients.append(alpha)

        logits = self.outc(out)
        return (logits, coefficients) if return_attention else logits


def plain_unet(
    in_channels: int = 16,
    num_classes: int = 5,
    features: Sequence[int] = (32, 64, 128, 256),
    *,
    bilinear: bool = True,
) -> AttentionUNet:
    """The same network with the gates removed.

    Section 7.5 requires the two to be compared. Building the baseline from
    the same class makes that a **controlled** comparison: identical depth,
    widths, normalisation and upsampling, differing only in the attention
    gates. A separately sourced baseline would confound the gates with every
    other implementation difference.

    (``segmentation_models_pytorch`` is the brief's suggested baseline and is
    still usable via ``models.unet``; this one exists so the ablation is
    clean.)
    """
    return AttentionUNet(
        in_channels=in_channels,
        num_classes=num_classes,
        features=features,
        bilinear=bilinear,
        attention=False,
    )


def count_parameters(model: nn.Module, *, trainable_only: bool = True) -> int:
    """Parameter count, for reporting the cost of the gates."""
    return sum(
        p.numel()
        for p in model.parameters()
        if p.requires_grad or not trainable_only
    )
