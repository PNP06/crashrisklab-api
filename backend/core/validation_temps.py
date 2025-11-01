from __future__ import annotations

from dataclasses import dataclass
from typing import Generator, Tuple

import numpy as np
import random as _random


def seed_all(seed: int = 42) -> None:
    np.random.seed(seed)
    try:
        import random

        random.seed(seed)
    except Exception:
        pass


@dataclass
class TimeSeriesSplitStrict:
    n_splits: int = 5
    min_test_size: int = 40

    def split(self, X) -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
        n = len(X)
        if self.n_splits <= 1 or n < self.min_test_size * 2:
            yield np.arange(0, n - self.min_test_size), np.arange(n - self.min_test_size, n)
            return
        test_size = max(self.min_test_size, int(n * 0.1))
        step = int((n - test_size) / self.n_splits)
        for i in range(self.n_splits):
            end_train = test_size + i * step
            if end_train <= test_size:
                continue
            train_idx = np.arange(0, end_train)
            test_idx = np.arange(end_train, min(n, end_train + test_size))
            if len(test_idx) < self.min_test_size:
                continue
            yield train_idx, test_idx

