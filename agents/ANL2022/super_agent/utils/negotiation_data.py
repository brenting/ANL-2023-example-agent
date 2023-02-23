from typing import List


class NegotiationData:
    tSplit: int = 40

    def __init__(self, max_received_util=0.0, agreement_util=0.0, opponent_name='', opponent_util=0.0,
                 opponent_util_by_time=None):
        self._max_received_util: float = max_received_util
        self._agreement_util: float = agreement_util
        self._opponent_name: str = opponent_name
        self._opponent_util: float = opponent_util
        if opponent_util_by_time is None:
            self._opponent_util_by_time: List[float] = [0.0] * NegotiationData.tSplit
        else:
            self._opponent_util_by_time: List[float] = opponent_util_by_time

    def add_agreement_util(self, agreement_util: float):
        self._agreement_util = agreement_util
        if agreement_util > self._max_received_util:
            self._max_received_util = agreement_util

    def add_bid_util(self, bid_util: float):
        if bid_util > self._max_received_util:
            self._max_received_util = bid_util

    def update_opponent_offers(self, op_sum: List[float], op_counts: List[int]):
        for i in range(NegotiationData.tSplit):
            self._opponent_util_by_time[i] = op_sum[i] / op_counts[i] if op_counts[i] > 0 else 0.0

    def set_opponent_name(self, opponent_name: str):
        self._opponent_name = opponent_name

    def set_opponent_util(self, opp_util: float):
        self._opponent_util = opp_util

    def get_opponent_name(self):
        return self._opponent_name

    def get_max_received_util(self):
        return self._max_received_util

    def get_agreement_util(self):
        return self._agreement_util

    def get_opponent_util(self):
        return self._opponent_util

    def get_opponent_util_by_time(self):
        return self._opponent_util_by_time
