"""Tests for src.retry — RetryConfig with fixed and exponential strategies."""

from __future__ import annotations

from unittest.mock import patch

from src.retry import RetryConfig


class TestRetryConfigDefaults:
    def test_default_values(self):
        cfg = RetryConfig()
        assert cfg.max_attempts == 5
        assert cfg.strategy == "exponential"
        assert cfg.base_delay == 2.0
        assert cfg.max_delay == 60.0

    def test_frozen(self):
        cfg = RetryConfig()
        try:
            cfg.max_attempts = 10  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError:
            pass


class TestFixedStrategy:
    def test_constant_delay(self):
        cfg = RetryConfig(strategy="fixed", base_delay=3.0)
        assert cfg.delay(0) == 3.0
        assert cfg.delay(1) == 3.0
        assert cfg.delay(5) == 3.0
        assert cfg.delay(99) == 3.0

    def test_ignores_max_delay(self):
        cfg = RetryConfig(strategy="fixed", base_delay=100.0, max_delay=10.0)
        assert cfg.delay(0) == 100.0


class TestExponentialStrategy:
    def test_growth(self):
        cfg = RetryConfig(strategy="exponential", base_delay=2.0, max_delay=60.0)
        with patch("src.retry.random.uniform", return_value=0.0):
            assert cfg.delay(0) == 2.0
            assert cfg.delay(1) == 4.0
            assert cfg.delay(2) == 8.0
            assert cfg.delay(3) == 16.0

    def test_capped_at_max(self):
        cfg = RetryConfig(strategy="exponential", base_delay=2.0, max_delay=10.0)
        with patch("src.retry.random.uniform", return_value=0.0):
            assert cfg.delay(10) == 10.0

    def test_jitter_added(self):
        cfg = RetryConfig(strategy="exponential", base_delay=2.0, max_delay=60.0)
        with patch("src.retry.random.uniform", return_value=0.5):
            assert cfg.delay(0) == 2.5  # 2.0 + 0.5

    def test_jitter_range(self):
        """Jitter is uniform(0, delay/2)."""
        cfg = RetryConfig(strategy="exponential", base_delay=2.0, max_delay=60.0)
        with patch("src.retry.random.uniform") as mock_uniform:
            mock_uniform.return_value = 3.0
            result = cfg.delay(2)  # base delay = 8.0
            mock_uniform.assert_called_once_with(0, 4.0)  # half of 8.0
        assert result == 11.0  # 8.0 + 3.0


class TestCustomConfigs:
    def test_single_attempt(self):
        cfg = RetryConfig(max_attempts=1)
        assert cfg.max_attempts == 1

    def test_custom_exponential(self):
        cfg = RetryConfig(max_attempts=3, base_delay=1.0, max_delay=10.0)
        with patch("src.retry.random.uniform", return_value=0.0):
            assert cfg.delay(0) == 1.0
            assert cfg.delay(1) == 2.0
            assert cfg.delay(2) == 4.0
