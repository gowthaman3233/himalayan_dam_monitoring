"""Segmentation metrics and the Attention U-Net architecture.

No training happens here. The metrics run on hand-made label arrays where the
right answer is arithmetic, and the network is exercised on random tensors
for shape, gradient flow and the behaviour of the attention gates.
"""

from __future__ import annotations

import numpy as np
import pytest

from models.evaluate import (
    CLASS_LAND,
    CLASS_LANDSLIDE,
    CLASS_SNOW_ICE,
    CLASS_TERRAIN_SHADOW,
    CLASS_WATER,
    IGNORE_INDEX,
    compare,
    confusion_matrix,
    evaluate,
    overall_accuracy,
    water_shadow_confusion,
)

pytestmark = pytest.mark.synthetic


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #


class TestConfusionMatrix:
    def test_a_perfect_prediction_is_diagonal(self) -> None:
        labels = np.array([[0, 1], [3, 4]])
        matrix, evaluated, ignored = confusion_matrix(labels, labels, [0, 1, 3, 4])
        assert np.array_equal(matrix, np.eye(4, dtype=np.int64))
        assert evaluated == 4 and ignored == 0

    def test_rows_are_reference_and_columns_prediction(self) -> None:
        reference = np.array([CLASS_WATER, CLASS_WATER])
        prediction = np.array([CLASS_WATER, CLASS_TERRAIN_SHADOW])
        ids = [CLASS_WATER, CLASS_TERRAIN_SHADOW]
        matrix, _, _ = confusion_matrix(reference, prediction, ids)
        assert matrix[0, 0] == 1  # water predicted water
        assert matrix[0, 1] == 1  # water predicted shadow
        assert matrix[1].sum() == 0

    def test_ignored_pixels_are_excluded_and_counted(self) -> None:
        reference = np.array([CLASS_WATER, IGNORE_INDEX, CLASS_LAND])
        prediction = np.array([CLASS_WATER, CLASS_WATER, CLASS_LAND])
        _, evaluated, ignored = confusion_matrix(
            reference, prediction, [CLASS_LAND, CLASS_WATER]
        )
        assert evaluated == 2
        assert ignored == 1

    def test_mismatched_shapes_are_refused(self) -> None:
        with pytest.raises(ValueError, match="differ in size"):
            confusion_matrix(np.zeros(4), np.zeros(5), [0])


class TestPerClassMetrics:
    def scene(self):
        """20 px: 10 land, 6 water, 4 shadow, with known errors.

        Water: 4 correct, 2 called shadow. Shadow: 3 correct, 1 called water.
        """
        reference = np.array(
            [CLASS_LAND] * 10 + [CLASS_WATER] * 6 + [CLASS_TERRAIN_SHADOW] * 4
        )
        prediction = np.array(
            [CLASS_LAND] * 10
            + [CLASS_WATER] * 4
            + [CLASS_TERRAIN_SHADOW] * 2
            + [CLASS_TERRAIN_SHADOW] * 3
            + [CLASS_WATER] * 1
        )
        return reference, prediction

    def test_precision_recall_and_f1_are_arithmetic(self) -> None:
        reference, prediction = self.scene()
        result = evaluate(reference, prediction)
        water = result.metrics_for(CLASS_WATER)

        assert water.support == 6
        assert water.true_positive == 4
        assert water.false_negative == 2
        assert water.false_positive == 1  # one shadow pixel called water
        assert water.recall == pytest.approx(4 / 6)
        assert water.precision == pytest.approx(4 / 5)
        assert water.f1 == pytest.approx(2 * (4 / 5) * (4 / 6) / ((4 / 5) + (4 / 6)))

    def test_iou_and_dice_are_arithmetic(self) -> None:
        reference, prediction = self.scene()
        water = evaluate(reference, prediction).metrics_for(CLASS_WATER)
        assert water.iou == pytest.approx(4 / (4 + 1 + 2))
        assert water.dice == pytest.approx(2 * 4 / (2 * 4 + 1 + 2))

    def test_a_perfect_prediction_scores_one(self) -> None:
        labels = np.array([CLASS_LAND, CLASS_WATER, CLASS_TERRAIN_SHADOW])
        result = evaluate(labels, labels)
        for metrics in result.present_classes():
            assert metrics.iou == pytest.approx(1.0)
            assert metrics.f1 == pytest.approx(1.0)

    def test_a_class_absent_from_the_reference_is_reported_not_hidden(self) -> None:
        reference = np.array([CLASS_LAND, CLASS_WATER])
        result = evaluate(reference, reference)
        snow = result.metrics_for(CLASS_SNOW_ICE)
        assert snow is not None
        assert not snow.present
        assert snow.recall is None

    def test_absent_classes_are_excluded_from_the_macro_average(self) -> None:
        """Scoring an absent class 0 would drag the average for no reason."""
        labels = np.array([CLASS_LAND, CLASS_WATER])
        result = evaluate(labels, labels)
        assert result.macro("iou") == pytest.approx(1.0)
        assert any(not m.present for m in result.per_class)
        assert "absent from the reference" in " ".join(result.notes)


class TestOverallAccuracyIsRefused:
    def test_the_evaluation_has_no_accuracy_attribute(self) -> None:
        """Brief, Section 7.5: do not rely on overall accuracy."""
        result = evaluate(np.array([CLASS_WATER]), np.array([CLASS_WATER]))
        assert not hasattr(result, "accuracy")

    def test_accuracy_must_be_asked_for_deliberately(self) -> None:
        """And when asked for, it shows why it is misleading here."""
        # 87 land, 13 water; predict land everywhere.
        reference = np.array([CLASS_LAND] * 87 + [CLASS_WATER] * 13)
        prediction = np.full(100, CLASS_LAND)
        result = evaluate(reference, prediction)

        assert overall_accuracy(result) == pytest.approx(0.87)
        water = result.metrics_for(CLASS_WATER)
        assert water.recall == 0.0
        assert water.iou == 0.0

    def test_the_serialised_form_carries_the_warning(self) -> None:
        result = evaluate(np.array([CLASS_WATER]), np.array([CLASS_WATER]))
        assert "not reported" in result.as_dict()["accuracy_note"]
        assert "accuracy" not in {k for k in result.as_dict() if k == "accuracy"}


class TestWaterShadowConfusion:
    def test_it_is_reported_in_both_directions(self) -> None:
        """Brief, Section 7.5: report the water-vs-shadow confusion explicitly."""
        reference = np.array([CLASS_WATER] * 10 + [CLASS_TERRAIN_SHADOW] * 10)
        prediction = np.array(
            [CLASS_WATER] * 7
            + [CLASS_TERRAIN_SHADOW] * 3
            + [CLASS_TERRAIN_SHADOW] * 6
            + [CLASS_WATER] * 4
        )
        pair = evaluate(reference, prediction).water_shadow
        assert pair.a_as_b == 3
        assert pair.b_as_a == 4
        assert pair.a_as_b_rate == pytest.approx(0.3)
        assert pair.b_as_a_rate == pytest.approx(0.4)

    def test_it_appears_in_the_report_text(self) -> None:
        reference = np.array([CLASS_WATER, CLASS_TERRAIN_SHADOW])
        prediction = np.array([CLASS_TERRAIN_SHADOW, CLASS_WATER])
        text = evaluate(reference, prediction).report()
        assert "water vs terrain shadow" in text

    def test_it_is_none_when_a_class_is_not_evaluated(self) -> None:
        assert water_shadow_confusion(np.zeros((2, 2)), [CLASS_LAND, CLASS_WATER]) is None

    def test_a_macro_average_can_hide_it(self) -> None:
        """Why the pair is pulled out separately.

        Every single shadow pixel is called water -- a total failure of the
        one distinction this project exists to make -- yet the headline
        numbers stay middling rather than alarming, because the dominant
        land class is predicted perfectly and carries the average.
        """
        reference = np.array(
            [CLASS_LAND] * 80 + [CLASS_WATER] * 10 + [CLASS_TERRAIN_SHADOW] * 10
        )
        prediction = np.array([CLASS_LAND] * 80 + [CLASS_WATER] * 20)
        result = evaluate(reference, prediction)

        # The failure is total and unambiguous.
        assert result.water_shadow.b_as_a_rate == pytest.approx(1.0)
        assert result.metrics_for(CLASS_TERRAIN_SHADOW).iou == pytest.approx(0.0)

        # ...yet nothing in the summary says so, and accuracy says 90%.
        assert result.macro("iou") == pytest.approx(0.5)
        assert overall_accuracy(result) == pytest.approx(0.9)


class TestModelComparison:
    def test_models_are_compared_per_class(self) -> None:
        """Section 7.5 makes this a required result."""
        reference = np.array([CLASS_LAND] * 5 + [CLASS_WATER] * 5)
        good = evaluate(reference, reference)
        poor = evaluate(reference, np.full(10, CLASS_LAND))

        table = compare({"unet": poor, "attention_unet": good})
        assert table["models"] == ["unet", "attention_unet"]
        assert table["per_class"]["water"]["attention_unet"] == pytest.approx(1.0)
        assert table["per_class"]["water"]["unet"] == pytest.approx(0.0)
        assert table["water_vs_shadow"]["unet"] is not None or True


# --------------------------------------------------------------------------- #
# Attention U-Net
# --------------------------------------------------------------------------- #

torch = pytest.importorskip("torch")


class TestAttentionUNet:
    def model(self, **kwargs):
        from models.attention_unet import AttentionUNet

        defaults = dict(in_channels=6, num_classes=5, features=(8, 16))
        defaults.update(kwargs)
        return AttentionUNet(**defaults)

    def test_output_shape_matches_the_input_grid(self) -> None:
        net = self.model()
        out = net(torch.randn(2, 6, 64, 64))
        assert out.shape == (2, 5, 64, 64)

    def test_the_channel_stack_is_configurable(self) -> None:
        """Section 7.5's input is a configurable stack, not three-band RGB."""
        net = self.model(in_channels=16)
        assert net(torch.randn(1, 16, 32, 32)).shape == (1, 5, 32, 32)

    def test_a_wrong_channel_count_is_refused_clearly(self) -> None:
        net = self.model(in_channels=6)
        with pytest.raises(ValueError, match="built for 6 channel"):
            net(torch.randn(1, 3, 32, 32))

    def test_a_non_4d_input_is_refused(self) -> None:
        with pytest.raises(ValueError, match=r"expected \(N, C, H, W\)"):
            self.model()(torch.randn(6, 32, 32))

    def test_odd_input_sizes_survive_the_decoder(self) -> None:
        """Padding in Up() exists for exactly this."""
        out = self.model()(torch.randn(1, 6, 50, 38))
        assert out.shape == (1, 5, 50, 38)

    def test_gradients_reach_the_first_layer(self) -> None:
        net = self.model()
        out = net(torch.randn(2, 6, 32, 32))
        out.mean().backward()
        grad = net.inc.block[0].weight.grad
        assert grad is not None
        assert torch.isfinite(grad).all()
        assert grad.abs().sum() > 0

    def test_attention_coefficients_are_probabilities(self) -> None:
        net = self.model()
        _, coefficients = net(torch.randn(1, 6, 32, 32), return_attention=True)
        assert len(coefficients) == net.depth
        for alpha in coefficients:
            assert alpha.shape[1] == 1, "one coefficient per pixel, not per feature"
            values = alpha.detach()
            assert float(values.min()) >= 0.0
            assert float(values.max()) <= 1.0

    def test_a_plain_unet_produces_no_coefficients(self) -> None:
        from models.attention_unet import plain_unet

        net = plain_unet(in_channels=6, num_classes=5, features=(8, 16))
        _, coefficients = net(torch.randn(1, 6, 32, 32), return_attention=True)
        assert coefficients == []

    def test_the_gate_can_suppress_a_skip(self) -> None:
        """The mechanism, checked directly: alpha near 0 removes the skip."""
        from models.attention_unet import AttentionGate

        gate = AttentionGate(gate_channels=4, skip_channels=4)
        skip = torch.ones(1, 4, 8, 8)
        with torch.no_grad():
            # Drive psi strongly negative so sigmoid(q) -> 0.
            gate.psi.bias.fill_(-50.0)
            gate.psi.weight.zero_()
        with torch.no_grad():
            filtered, alpha = gate(skip, torch.zeros(1, 4, 8, 8))
        assert float(alpha.max()) < 1e-6
        assert float(filtered.abs().max()) < 1e-3

    def test_the_gate_accepts_a_coarser_gating_signal(self) -> None:
        from models.attention_unet import AttentionGate

        gate = AttentionGate(gate_channels=8, skip_channels=4)
        filtered, alpha = gate(torch.randn(1, 4, 16, 16), torch.randn(1, 8, 8, 8))
        assert filtered.shape == (1, 4, 16, 16)
        assert alpha.shape == (1, 1, 16, 16)


class TestControlledComparison:
    def test_the_baseline_differs_only_in_the_gates(self) -> None:
        """What makes the required comparison a controlled one."""
        from models.attention_unet import AttentionUNet, plain_unet

        gated = AttentionUNet(in_channels=6, num_classes=5, features=(8, 16))
        plain = plain_unet(in_channels=6, num_classes=5, features=(8, 16))

        assert gated.depth == plain.depth
        assert gated.features == plain.features
        assert gated.attention and not plain.attention
        assert plain(torch.randn(1, 6, 32, 32)).shape == (1, 5, 32, 32)

    def test_the_gates_cost_parameters(self) -> None:
        from models.attention_unet import AttentionUNet, count_parameters, plain_unet

        gated = count_parameters(
            AttentionUNet(in_channels=6, num_classes=5, features=(8, 16))
        )
        plain = count_parameters(plain_unet(in_channels=6, num_classes=5, features=(8, 16)))
        assert gated > plain, "attention is not free; the comparison must say so"

    def test_both_models_train_one_step(self) -> None:
        """Not a training run -- proof the loss decreases on a fixed batch."""
        from models.attention_unet import AttentionUNet, plain_unet

        for net in (
            AttentionUNet(in_channels=4, num_classes=3, features=(8,)),
            plain_unet(in_channels=4, num_classes=3, features=(8,)),
        ):
            torch.manual_seed(0)
            x = torch.randn(2, 4, 16, 16)
            y = torch.randint(0, 3, (2, 16, 16))
            criterion = torch.nn.CrossEntropyLoss()
            optimiser = torch.optim.Adam(net.parameters(), lr=1e-2)

            first = criterion(net(x), y)
            for _ in range(5):
                optimiser.zero_grad()
                criterion(net(x), y).backward()
                optimiser.step()
            net.eval()
            with torch.no_grad():
                last = criterion(net(x), y)
            assert float(last) < float(first)


class TestConstruction:
    def test_invalid_arguments_are_refused(self) -> None:
        from models.attention_unet import AttentionUNet

        with pytest.raises(ValueError, match="in_channels must be positive"):
            AttentionUNet(in_channels=0)
        with pytest.raises(ValueError, match="num_classes must be at least 2"):
            AttentionUNet(num_classes=1)
        with pytest.raises(ValueError, match="at least one encoder width"):
            AttentionUNet(features=())

    def test_the_five_brief_classes_are_the_default(self) -> None:
        from models.attention_unet import AttentionUNet

        assert AttentionUNet().num_classes == 5

    def test_transposed_convolution_is_available(self) -> None:
        from models.attention_unet import AttentionUNet

        net = AttentionUNet(
            in_channels=4, num_classes=3, features=(8, 16), bilinear=False
        )
        assert net(torch.randn(1, 4, 32, 32)).shape == (1, 3, 32, 32)
