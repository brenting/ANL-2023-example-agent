from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.opponentmodel.OpponentModel import OpponentModel
from decimal import Decimal
from decimal import Context
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
                 freqs: Dict[str, Dict[Value, float]], total: int,
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

    @staticmethod
    def create() -> "FrequencyOpponentModel":
        return FrequencyOpponentModel(None, {}, 0, None)

    # Override
    def With(self, newDomain: Domain, newResBid: Optional[Bid]) -> "FrequencyOpponentModel":
        if newDomain == None:
            raise ValueError("domain is not initialized")
        # FIXME merge already available frequencies?
        return FrequencyOpponentModel(newDomain,
                                      {iss: {} for iss in newDomain.getIssues()},
                                      0, newResBid)

    # Override
    def getUtility(self, bid: Bid) -> Decimal:
        if self._domain == None:
            raise ValueError("domain is not initialized")
        if self._totalBids == 0:
            return Decimal(1)
        sum = Decimal(0)

        # Assume different weights
        dict = self.getWeight()


        for issue in val(self._domain).getIssues():
            if issue in bid.getIssues():
                # Using estimated weights, compute the utility of the opponent for a given bid.
                sum = sum + Context.multiply(Context(), self._getFraction(issue, val(bid.getValue(issue))),
                                             Decimal.from_float(dict[issue]))

        return round(sum, FrequencyOpponentModel._DECIMALS)

    # Override
    def getName(self) -> str:
        if self._domain == None:
            raise ValueError("domain is not initialized")
        return "FreqOppModel" + str(hash(self)) + "For" + str(self._domain)

    # Override
    def getDomain(self) -> Domain:
        return val(self._domain)

    # Override
    def WithAction(self, action: Action, progress: Progress) -> "FrequencyOpponentModel":
        if self._domain == None:
            raise ValueError("domain is not initialized")

        if not isinstance(action, Offer):
            return self

        # Method altered so that it computes utilities in a more accurate way than just frequencies.
        bid: Bid = action.getBid()
        newFreqs: Dict[str, Dict[Value, float]] = self.cloneMap(self._bidFrequencies)
        for issue in self._domain.getIssues():  # type:ignore
            freqs: Dict[Value, float] = newFreqs[issue]
            values_in_issue = len(newFreqs[issue])
            value = bid.getValue(issue)
            avg_value = 0.5
            if value != None:
                oldfreq = 0
                if value in freqs:
                    oldfreq = freqs[value]

                for i in freqs:
                    if freqs[i] == 0:
                        freqs[i] = avg_value

                freqs[value] = oldfreq + 0.05  # type:ignore
                if freqs[value] > 1:
                    freqs[value] = 1
                factor = values_in_issue * avg_value / sum(freqs.values())
                for k in freqs:
                    freqs[k] = freqs[k] * factor

        return FrequencyOpponentModel(self._domain, newFreqs,
                                      self._totalBids + 1, self._resBid)

    def getCounts(self, issue: str) -> Dict[Value, float]:
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
            return Decimal(0.5)
            # return Decimal(1)
        if not (issue in self._bidFrequencies and value in self._bidFrequencies[issue]):
            return Decimal(0)

        return Decimal(self._bidFrequencies[issue][value])

        # return round((Decimal(freq) / self._totalBids), FrequencyOpponentModel._DECIMALS)  # type:ignore

    @staticmethod
    def cloneMap(freqs: Dict[str, Dict[Value, float]]) -> Dict[str, Dict[Value, float]]:
        '''
        @param freqs
        @return deep copy of freqs map.
        '''
        map: Dict[str, Dict[Value, float]] = {}
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


    def toString(self):
        return f"FrequencyOpponentModel({self._totalBids}, {self._bidFrequencies}"

    # Obtain estimated weights of issues for the opponent.
    def getWeight(self):
        dict = {}
        total_sum = 0
        for issue in val(self._domain).getIssues():
            # get freq of the values used in every issue
            hash = self.getCounts(issue)

            # pick out the max freq of the values from each issue
            value_with_highest_frequency = max(hash, key=hash.get)
            dict[issue] = hash[value_with_highest_frequency]
            # keep track of total sum of "weights" (frequencies)
            total_sum += dict[issue]

        if total_sum == 0:
            for issue in dict:
                dict[issue] = 0

        # get their "relative importance", relative to all other max frequencies from the other issue
        else:
            for issue in dict:
                dict[issue] = (dict[issue] / total_sum)
        return dict