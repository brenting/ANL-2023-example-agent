from decimal import Decimal
from geniusweb.bidspace.BidsWithUtility import BidsWithUtility
from geniusweb.bidspace.Interval import Interval
from geniusweb.issuevalue.Bid import Bid
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList
from typing import List


class ExtendedUtilSpace:
    def __init__(self, space: LinearAdditive):
        self.util_space = space
        self.bid_utils = BidsWithUtility.create(self.util_space)
        self.tolerance = self.compute_tolerance()

    def compute_tolerance(self) -> Decimal:
        tolerance = Decimal(1)
        for iss in self.bid_utils.getInfo():
            if iss.getValues().size() > 1:
                # we have at least 2 values.
                values: List[Decimal] = []
                for val in iss.getValues():
                    values.append(iss.getWeightedUtil(val))
                values.sort()
                values.reverse()
                tolerance = min(tolerance, values[0] - values[1])
        return tolerance

    def getBids(self, utilityGoal: Decimal, time: float) -> ImmutableList[Bid]:
        return self.bid_utils.getBids(
            Interval(utilityGoal - (Decimal(time)*3 + 1)*self.tolerance, utilityGoal + (Decimal(time)*3 + 1)*self.tolerance)
        )
