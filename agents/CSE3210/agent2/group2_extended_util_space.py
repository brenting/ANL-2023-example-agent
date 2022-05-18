from geniusweb.bidspace.BidsWithUtility import BidsWithUtility
from geniusweb.bidspace.Interval import Interval
from geniusweb.bidspace.IssueInfo import IssueInfo
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Value import Value
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList
from decimal import Decimal
from typing import List


class ExtendedUtilSpace:
    """
    Inner class for TimeDependentParty, made public for testing purposes. This
    class may change in the future, use at your own risk.
    """

    def __init__(self, space: LinearAdditive):
        self._utilspace = space
        self._bidutils = BidsWithUtility.create(self._utilspace)
        self._computeMinMax()
        self._tolerance = self._computeTolerance()

    def _computeMinMax(self):
        """
        Computes the fields minutil and maxUtil.
        <p>
        TODO this is simplistic, very expensive method and may cause us to run
        out of time on large domains.
        <p>
        Assumes that utilspace and bidutils have been set properly.
        """
        range = self._bidutils.getRange()
        self._minUtil = range.getMin()
        self._maxUtil = range.getMax()

        rvbid = self._utilspace.getReservationBid()
        if rvbid != None:
            rv = self._utilspace.getUtility(rvbid)
            if rv > self._minUtil:
                self._minUtil = rv

    def _computeTolerance(self) -> Decimal:
        """
        Tolerance is the Interval we need when searching bids. When we are close
        to the maximum utility, this value has to be the distance between the
        best and one-but-best utility.

        @return the minimum tolerance required, which is the minimum difference
                between the weighted utility of the best and one-but-best issue
                value.
        """
        tolerance = Decimal(1)
        for iss in self._bidutils.getInfo():
            if iss.getValues().size() > 1:
                # we have at least 2 values.
                values: List[Decimal] = []
                for val in iss.getValues():
                    values.append(iss.getWeightedUtil(val))
                values.sort()
                values.reverse()
                tolerance = min(tolerance, values[0] - values[1])
        return tolerance

    def getMin(self) -> Decimal:
        return self._minUtil

    def getMax(self) -> Decimal:
        return self._maxUtil

    def getBids(self, utilityGoal: Decimal) -> ImmutableList[Bid]:
        """
        @param utilityGoal the requested utility
        @return bids with utility inside [utilitygoal-{@link #tolerance},
                utilitygoal]
        """
        return self._bidutils.getBids(
            Interval(utilityGoal - self._tolerance, utilityGoal)
        )
