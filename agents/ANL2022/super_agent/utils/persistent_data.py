from abc import ABC
from collections import defaultdict
from typing import List
from .negotiation_data import NegotiationData
import math


class PersistentData(ABC):
    def __init__(self):
        self._t_split: int = 40
        self._t_phase: float = 0.2
        self._new_weight: float = 0.3
        self._smooth_width: int = 3
        self._opponent_decrease: float = 0.65
        self._default_alpha: float = 10.7

        self._avg_utility: float = 0.0
        self._negotiations: int = 0
        # dictionary ["string"] -> float
        self._avg_max_utility_opponent = defaultdict()
        # dictionary ["string"] -> int
        self._opponent_encounters = defaultdict()

        self._std_utility: float = 0.0
        self._nego_results: List[float] = []

        self._avg_opponent_utility = defaultdict()
        self._opponent_alpha = defaultdict()
        self._opponent_utility_by_time = defaultdict()

    def update(self, negotiation_data: NegotiationData):
        new_util = negotiation_data.get_agreement_util() if negotiation_data.get_agreement_util() > 0 else (
                self._avg_utility - 1.1 * math.pow(self._std_utility, 2))
        self._avg_utility = (self._avg_utility * self._negotiations + new_util) / (self._negotiations + 1)

        self._negotiations += 1

        self._nego_results.append(negotiation_data.get_agreement_util())
        self._std_utility = 0.0

        for util in self._nego_results:
            self._std_utility += math.pow(util - self._avg_utility, 2)
        self._std_utility = math.sqrt(self._std_utility / self._negotiations)

        opponent = negotiation_data.get_opponent_name()

        if opponent is not None:
            encounters = self._opponent_encounters.get(opponent) if opponent in self._opponent_encounters else 0
            self._opponent_encounters[opponent] = encounters + 1

            self._avg_utility = self._avg_max_utility_opponent.get(
                opponent) if opponent in self._avg_max_utility_opponent else 0.0

            self._avg_max_utility_opponent[opponent] = (
                    (self._avg_utility * encounters + negotiation_data.get_max_received_util()) / (encounters + 1))

            avg_op_util = self._avg_opponent_utility.get(opponent) if opponent in self._avg_opponent_utility else 0.0
            self._avg_opponent_utility[opponent] = (avg_op_util * encounters + negotiation_data.get_opponent_util()) / (
                    encounters + 1)

            opponent_time_util: List[float] = []
            if opponent in self._opponent_utility_by_time:
                opponent_time_util = self._opponent_utility_by_time.get(opponent)
            else:
                opponent_time_util = [0.0] * self._t_split

            new_util_data: List[float] = negotiation_data.get_opponent_util_by_time()

            ratio = ((1 - self._new_weight) * opponent_time_util[0] + self._new_weight * new_util_data[0]) / \
                    opponent_time_util[0] if opponent_time_util[0] > 0.0 else 1

            for i in range(self._t_split):
                if new_util_data[i] > 0:
                    opponent_time_util[i] = (
                            (1 - self._new_weight) * opponent_time_util[i] + self._new_weight * new_util_data[i])
                else:
                    opponent_time_util[i] *= ratio

        self._opponent_utility_by_time[opponent] = opponent_time_util
        self._opponent_alpha[opponent] = self._calc_alpha(opponent)

    def _known_opponent(self, opponent: str):
        return opponent in self._opponent_encounters

    def get_opponent_encounters(self, opponent):
        return self._opponent_encounters[opponent] if opponent in self._opponent_encounters else None

    def get_smooth_threshold_over_time(self, opponent: str):
        if not self._known_opponent(opponent):
            return None

        opponent_time_util = self._opponent_utility_by_time.get(opponent)
        smoothed_time_util: List[float] = [0.0] * self._t_split
        # for i in range(self._t_split):
        #     smoothed_time_util[i] = 0.0

        for i in range(self._t_split):
            for j in range(max(0, i - self._smooth_width), min(i + self._smooth_width + 1, self._t_split)):
                smoothed_time_util[i] += opponent_time_util[j]
            smoothed_time_util[i] /= (min(i + self._smooth_width + 1, self._t_split) - max(i - self._smooth_width, 0))

        return smoothed_time_util

    def _calc_alpha(self, opponent: str):
        alpha_arr = self.get_smooth_threshold_over_time(opponent)
        if alpha_arr is None:
            return self._default_alpha
        max_idx = 0
        t = 0
        for max_idx in range(self._t_split):
            if alpha_arr[max_idx] < 0.2:
                break

        max_val = alpha_arr[0]
        min_val = alpha_arr[max(max_idx - self._smooth_width - 1, 0)]
        if max_val - min_val < 0.1:
            return self._default_alpha

        for t in range(max_idx):
            if alpha_arr[t] <= (max_val - self._opponent_decrease * (max_val - min_val)):
                break

        calibrated_polynom = [572.83, -1186.7, 899.29, -284.68, 32.911]
        alpha = calibrated_polynom[0]
        t_time = self._t_phase + (1 - self._t_phase) * (
                max_idx * (t / self._t_split) + (self._t_split - max_idx) * 0.85) / self._t_split
        for i in range(1, len(calibrated_polynom)):
            alpha = alpha * t_time + calibrated_polynom[i]
        print("alpha={0}".format(alpha))
        return alpha

    def get_avg_max_utility(self, opponent: str):
        if opponent in self._avg_max_utility_opponent:
            return self._avg_max_utility_opponent[opponent]
        return None

    def get_opponent_utility(self, opponent):
        return self._avg_opponent_utility.get(opponent) if self._known_opponent(opponent) else 0.0

    def get_opponent_alpha(self, opponent):
        return self._opponent_alpha.get(opponent) if self._known_opponent(opponent) else 0.0

    def get_std_utility(self):
        return self._std_utility

    def get_avg_utility(self):
        return self._avg_utility
