from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from time import time
import random

class AcceptanceStrategy:

    def __init__(self, profile, progress):
        self._profile = profile
        self._progress = progress
        self._last_bid = None

    def accept_condition(self, bid: Bid) -> bool:
        if bid is None:
            return False
        # Progress of the negotiation session between 0 and 1 (1 is deadline).
        progress = self._progress.get(time() * 1000)

        # Calculate the utility of the current bid.
        utility = self._profile.getUtility(bid)

        # Determine the minimum acceptable utility based on the progress of the negotiation.
        min_utility = 1.0 - progress

        # If this is the first bid, accept it.
        if self._last_bid is None:
            self._last_bid = bid
            return True

        # If the bid is at least as good as the last bid made by us, accept it.
        if self._profile.getUtility(bid) >= self._profile.getUtility(self._last_bid):
            self._last_bid = bid
            return True

        # If the bid is close to the minimum acceptable utility, use a random threshold to decide.
        elif utility >= min_utility * 0.9:
            return random.random() < 0.5

        # Otherwise, reject the bid.
        else:
            return False
