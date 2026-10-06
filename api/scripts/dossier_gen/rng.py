"""Single seeded randomness source for the generator.

Everything that varies between processors or documents — amounts, dates,
names drawn from a pool, weighbridge-photo degradation parameters — must
come from the one Random instance created here. Never use the global
`random` module, an unseeded `numpy` generator, or wall-clock time: the
generator must produce byte-identical ground_truth.json and manifests
across runs with the same seed.
"""

import random


def new_rng(seed: int) -> random.Random:
    return random.Random(seed)
