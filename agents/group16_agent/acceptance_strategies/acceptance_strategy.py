from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from time import time
import random


class AcceptanceStrategy:

    def __init__(self, profile, progress):
        self._profile = profile
        self._progress = progress
        self._last_bid = None
        self._reservation_value = 0.3

    def accept_condition(self, bid: Bid) -> bool:
        if bid is None:
            return False
        # Progress of the negotiation session between 0 and 1 (1 is deadline).
        progress = self._progress.get(time() * 1000)

        # Calculate the utility of the current bid.
        utility = self._profile.getUtility(bid)

        # Determine the minimum acceptable utility based on the progress of the negotiation.
        min_utility = 1.0 - (progress / 3.0)

        if utility >= min_utility:
            return True

        # If the bid is close to the minimum acceptable utility, use a random threshold to decide.
        if utility >= min_utility * 0.9:
            return random.uniform(0, 1) < 0.5

        # Check if the time remaining is less than the ACtime(T) threshold.
        if progress >= 0.90 and utility >= self._reservation_value:
            return True

        # Otherwise, reject the bid.
        else:
            return False


        # # If the bid is at least as good as the last bid made by us, accept it.
        # if self._profile.getUtility(bid) >= self._profile.getUtility(self._last_bid):
        #     self._last_bid = bid
        #     return True