from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from time import time


class AcceptanceStrategy:

    def __init__(self, profile, progress):
        self._profile = profile
        self._progress = progress

    def accept_condition(self, bid: Bid) -> bool:
        if bid is None:
            return False

        # progress of the negotiation session between 0 and 1 (1 is deadline)
        progress = self._progress.get(time() * 1000)

        # very basic approach that accepts if the offer is valued above 0.7 and
        # 95% of the time towards the deadline has passed
        conditions = [
            self._profile.getUtility(bid) > 0.8,
            progress > 0.95,
        ]
        return all(conditions)