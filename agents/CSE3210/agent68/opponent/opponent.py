from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain

class Opponent:

    def __init__(self):
        self._domain: Domain = None
        self._freqDict: dict = {}
        self._allBids = []
        self._lastBid: Bid = None
        self._firstBid: Bid = None
        self._changed_issues = set()
        # self._currentBid: Bid = None

    def init_domain(self, domain: Domain):
        """
        Initialize the domain.

        :param domain: The domain.
        """
        self._domain = domain
        initValue = 1 / len(self._domain.getIssues())
        for issue in domain.getIssues():
            self._freqDict[issue] = initValue

    def log_bid(self, bid: Bid):
        """
        Main method of the opponent class
        it handles logging the bids the opponent made
        for learning purposes.

        :param bid: The bid that the agent received. 
        """
        if self._firstBid is None:
            self._firstBid = bid
        self._update_freq_dict(bid, 0.1)
        self._allBids.append(bid)
        self._lastBid = bid

    def get_issue_weight(self, issue: str) -> float:
        return self._freqDict[issue]

    def get_value_weight(self, issue: str, value: str) -> float:
        return 1 / len(self._domain.getValues(issue))

    def get_utility(self, bid: Bid) -> float:
        """
        Given a bid return the predicted utility

        :param bid: The bid to calculate utility value on.
        """
        pass

    def _update_freq_dict(self, received_bid: Bid, step: float):
        if self._lastBid is None or received_bid is None:
            return

        for issue in received_bid.getIssues():
            # Might fail if we receive partial bid.
            if issue not in self._changed_issues and received_bid.getValue(issue) == self._firstBid.getValue(issue):
                self._freqDict[issue] += step
            else:
                self._changed_issues.add(issue)

        print("=========")
        print("Last bid: " + str(self._lastBid))
        print("Curr bid: " + str(received_bid))
        print("Before: " + str(self._freqDict))
        self._freqDict = self.normalize(self._freqDict, 1)
        print("After: " + str(self._freqDict))
        print("=========")

    def normalize(self, d: dict, target=1.0):
        raw = sum(d.values())
        factor = target / raw
        # d.items()
        return {key: value * factor for key, value in d.items()}

