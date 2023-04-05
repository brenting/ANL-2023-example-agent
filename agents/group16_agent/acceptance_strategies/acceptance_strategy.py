from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from time import time
import random


class AcceptanceStrategy:

    def __init__(self, profile, progress):
        self._profile = profile
        self._progress = progress
        self._reservation_value = 0.3
        self._bid_history = []

    def accept_condition(self, bid: Bid) -> bool:
        if bid is None:
            return False

        # Progress of the negotiation session between 0 and 1 (1 is deadline).
        progress = self._progress.get(time() * 1000)

        # Update the reservation value based on the current bid and the history of bids.
        self._bid_history.append(bid)

        # Calculate the utility of the current bid.
        utility = self._profile.getUtility(bid)

        # Determine the minimum acceptable utility based on the progress of the negotiation.
        min_utility = 1.0 - (progress / 3.0)
        print(min_utility)

        # Strictly exploring
        if progress < 0.05:
            return False

        # Exploratory TFT and Similarity-Based TFT
        # AC const(a)(b) = accept iff u(b) >= a
        if utility >= min_utility:
            return True

        # If the bid is close to the minimum acceptable utility, use a random threshold to decide.
        if utility >= min_utility * 0.9:
            return random.uniform(0, 1) < 0.6

        # Eager
        best_offer = max([self._profile.getUtility(bid) for bid in self._bid_history])
        # # If the bid is at least as good as the avg offered so far, accept it.
        if progress >= 0.90 and self._profile.getUtility(bid) >= best_offer:
            return True

        # Desperate
        # Check if the time remaining is less than the ACtime(T) threshold.
        # ACtime(T) is the fail safe mechanism: an agent may decide its better to have any deal
        if progress >= 0.95 and utility >= self._reservation_value:
            return True

        if progress >= 0.98:
            return True
        # Other se, reject the bid.
        else:
            return False
