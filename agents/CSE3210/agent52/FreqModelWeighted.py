from geniusweb.opponentmodel import FrequencyOpponentModel
from decimal import Decimal
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Bid import Bid
from typing import Dict, Optional
from geniusweb.issuevalue.Value import Value
from geniusweb.utils import val
import numpy as np


class FreqModelWeighted(FrequencyOpponentModel.FrequencyOpponentModel):

    def __init__(self, domain: Optional[Domain],
                 freqs: Dict[str, Dict[Value, int]], total: int,
                 resBid: Optional[Bid]):
        super.__init__(domain, freqs, total, resBid)

    # Override
    def getUtility(self, bid: Bid) -> Decimal:
        if self._domain == None:
            raise ValueError("domain is not initialized")
        if self._totalBids == 0:
            return Decimal(1)
        sum = Decimal(0)

        for issue in val(self._domain).getIssues():
            if issue in bid.getIssues():
                sum = sum + Decimal(self._issueWeights[issue]) * self._getFraction(issue, val(bid.getValue(issue)))
        return round(sum / len(self._bidFrequencies), FrequencyOpponentModel.FrequencyOpponentModel._DECIMALS)

    """
    Find issue weights by considering count of most occurring value in each domain and scaling their sum to be 1
    """
    def updateIssueWeights(self):
        self._issueWeights = {}
        totalWeights = 0.0
        for issue in val(self._domain).getIssues():
            freqs = []

            for value, count in self._bidFrequencies.get(issue).items():
                freqs.append(count)

            if len(freqs) <= 1:
                self._issueWeights[issue] = 1
            else:
                freqs = np.array(freqs) / self._totalBids
                self._issueWeights[issue] = np.max(freqs)
            totalWeights += self._issueWeights[issue]

        for issue, weight in self._issueWeights.items():
            self._issueWeights[issue] = weight / totalWeights

        return self._issueWeights

