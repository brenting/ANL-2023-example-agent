from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.opponentmodel.OpponentModel import OpponentModel
from decimal import Decimal
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Bid import Bid
from typing import Dict, Optional
from geniusweb.issuevalue.Value import Value
from geniusweb.actions.Action import Action
from geniusweb.progress.Progress import Progress
from geniusweb.actions.Offer import Offer
from geniusweb.references.Parameters import Parameters
from geniusweb.utils import val, HASH, toStr


class FrequencyOpponentModel(UtilitySpace, OpponentModel):
    '''
    implements an {@link OpponentModel} by counting frequencies of bids placed by
    the opponent.
    <p>
    NOTE: {@link NumberValue}s are also treated as 'discrete', so the frequency
    of one value does not influence the influence the frequency of nearby values
    (as you might expect as {@link NumberValueSetUtilities} is only affected by
    the endpoints).
    <p>
    immutable.
    '''

    _DECIMALS = 4  # accuracy of our computations.

    def __init__(self, domain: Optional[Domain],
                 freqs: Dict[str, Dict[Value, int]],  total: int,
                 resBid: Optional[Bid]):
        '''
        internal constructor. DO NOT USE, see create. Assumes the freqs keyset is
        equal to the available issues.

        @param domain the domain. Should not be None
        @param freqs  the observed frequencies for all issue values. This map is
                      assumed to be a fresh private-access only copy.
        @param total  the total number of bids contained in the freqs map. This
                      must be equal to the sum of the Integer values in the
                      {@link #bidFrequencies} for each issue (this is not
                      checked).
        @param resBid the reservation bid. Can be null
        '''
        self._domain = domain
        self._bidFrequencies = freqs
        self._totalBids = total
        self._resBid = resBid

        """
        These variables are dictionaries with all issues of the domain as their keys. '_BidsChangedFrequency' and
        '_previousIssueValue' are helper-structures to construct the final structure: '_issueWeights', which holds the
        estimated weight of any issue. 
        """
        self._BidsChangedFrequency = {
            key: 0 for key in self._bidFrequencies.keys()}
        self._previousIssueValue = {
            key: None for key in self._bidFrequencies.keys()}
        self._issueWeights = {key: Decimal(
            1/len(self._bidFrequencies)) for key in self._bidFrequencies.keys()}

    @staticmethod
    def create() -> "FrequencyOpponentModel":
        return FrequencyOpponentModel(None, {}, 0, None)

    # Override
    def With(self, newDomain: Domain,  newResBid: Optional[Bid]) -> "FrequencyOpponentModel":
        if newDomain == None:
            raise ValueError("domain is not initialized")
        # FIXME merge already available frequencies?
        return FrequencyOpponentModel(newDomain,
                                      {iss: {}
                                          for iss in newDomain.getIssues()},
                                      0, newResBid)

    """
   The original implementation provided by Geniusweb calculates the utility for a bid with equal weights for each issue:
   '1 / (all issues present in the domain)' Instead of that we now use individual weights for each issue. 
    """
    # Override

    def getUtility(self, bid: Bid) -> Decimal:
        if self._domain == None:
            raise ValueError("domain is not initialized")
        if self._totalBids == 0:
            return Decimal(1)
        sum = Decimal(0)

        for issue in val(self._domain).getIssues():
            if issue in bid.getIssues():
                sum += (self._issueWeights[issue] *
                        self._getFraction(issue, val(bid.getValue(issue))))
        return round(sum, FrequencyOpponentModel._DECIMALS)

    # Override
    def getName(self) -> str:
        if self._domain == None:
            raise ValueError("domain is not initialized")
        return "FreqOppModel" + str(hash(self)) + "For" + str(self._domain)

    # Override
    def getDomain(self) -> Domain:
        return val(self._domain)

    """
    Since this method updates the model with every offer, this is also where we update our
    weights-estimation-variables. 
    """
    # Override

    def WithAction(self,  action: Action,  progress: Progress) -> "FrequencyOpponentModel":
        if self._domain == None:
            raise ValueError("domain is not initialized")

        if not isinstance(action, Offer):
            return self

        bid: Bid = action.getBid()
        newFreqs: Dict[str, Dict[Value, int]
                       ] = self.cloneMap(self._bidFrequencies)
        for issue in self._domain.getIssues():  # type:ignore
            freqs: Dict[Value, int] = newFreqs[issue]
            value = bid.getValue(issue)
            if value != None:

                """"
                Added by group55:
                If this is the first time the issue is mentioned, we do not do anything.

                if the issue is mentioned before, but the value is not changed, we do not do anything. 

                if the issue is mentioned before and the value is changed, we update the 'bidsChangedFrequency' for
                that issue. 

                In any case, we do update the 'previousIssueValue' afterwards to now be the current value. 
                """
                if self._previousIssueValue[issue] is not None:
                    if self._previousIssueValue[issue] is not value:
                        self._BidsChangedFrequency[issue] += 1
                self._previousIssueValue[issue] = value

                """
                End of Group55 contribution.
                """

                oldfreq = 0
                if value in freqs:
                    oldfreq = freqs[value]
                freqs[value] = oldfreq + 1  # type:ignore

        """
        Added Group55:
        Now that all issues have been processed. We loop through them again to calculate their weights. 
        
        First of all, if the total amount in changes is less then the total amount of issues, we keep the default
        weights, which are all equal. This is because the calculation below is non-representative with little data. 
        Therefore, this way, at least all issues have had a change to be changed.
        
        After that point, all issues-weights are updated as follows:
        they are 1 - (the frequency of their changes divided by the total amount of changes of all issues). This way
        The more an issue has been changes, the lower the weight. At the end of the loop, all weights will sum up to 1.    
        """
        totalAmountOfChanges = sum(self._BidsChangedFrequency.values())
        if totalAmountOfChanges >= len(self._domain.getIssues()):
            for issue in self._domain.getIssues():
                self._issueWeights[issue] = Decimal(
                    1 - (self._BidsChangedFrequency / totalAmountOfChanges))

        """
        End of Group55 contribution
        """

        return FrequencyOpponentModel(self._domain, newFreqs,
                                      self._totalBids+1, self._resBid)

    def getCounts(self, issue: str) -> Dict[Value, int]:
        '''
        @param issue the issue to get frequency info for
        @return a map containing a map of values and the number of times that
                value was used in previous bids. Values that are possible but not
                in the map have frequency 0.
        '''
        if self._domain == None:
            raise ValueError("domain is not initialized")
        if not issue in self._bidFrequencies:
            return {}
        return dict(self._bidFrequencies.get(issue))  # type:ignore

    # Override
    def WithParameters(self, parameters: Parameters) -> OpponentModel:
        return self  # ignore parameters

    def _getFraction(self, issue: str, value: Value) -> Decimal:
        '''
        @param issue the issue to check
        @param value the value to check
        @return the fraction of the total cases that bids contained given value
                for the issue.
        '''
        if self._totalBids == 0:
            return Decimal(1)
        if not (issue in self._bidFrequencies and value in self._bidFrequencies[issue]):
            return Decimal(0)
        freq: int = self._bidFrequencies[issue][value]
        # type:ignore
        return round(Decimal(freq) / self._totalBids, FrequencyOpponentModel._DECIMALS)

    @staticmethod
    def cloneMap(freqs: Dict[str, Dict[Value, int]]) -> Dict[str, Dict[Value, int]]:
        '''
        @param freqs
        @return deep copy of freqs map.
        '''
        map: Dict[str, Dict[Value, int]] = {}
        for issue in freqs:
            map[issue] = dict(freqs[issue])
        return map

    # Override
    def getReservationBid(self) -> Optional[Bid]:
        return self._resBid

    def __eq__(self, other):
        return isinstance(other, self.__class__) and \
            self._domain == other._domain and \
            self._bidFrequencies == other._bidFrequencies and \
            self._totalBids == other._totalBids and \
            self._resBid == other._resBid

    def __hash__(self):
        return HASH((self._domain, self._bidFrequencies, self._totalBids, self._resBid))
    # Override

    # Override
    def __repr__(self) -> str:
        return "FrequencyOpponentModel[" + str(self._totalBids) + "," + \
               toStr(self._bidFrequencies) + "]"
