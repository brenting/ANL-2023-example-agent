import time
import numpy as np
from abc import abstractmethod

from geniusweb.issuevalue.Bid import Bid
from geniusweb.profile.Profile import Profile
from geniusweb.progress.Progress import Progress

from .utility import AgentUtility


class AbstractAcceptanceStrategy:
    """
    Abstract class enables us to efficiently test different acceptance strategies.
    """

    def __init__(self, profile: Profile = None, progress: Progress = None, utility: AgentUtility = None):
        self._profile = profile
        self._progress = progress
        self._utility = utility

    def set_profile(self, profile):
        self._profile = profile

    def set_progress(self, progress):
        self._progress = progress

    @abstractmethod
    def accept(self, bid: Bid):
        pass


class CombiAcceptanceStrategy(AbstractAcceptanceStrategy):
    """
    tested acceptance strategy, not the final one used, based on a combination of time based and if the bid is better than next.
    """

    def accept(self, bid: Bid):
        """
        acceptance strategy based on combination of time and is bid better than next.
        """
        progress = self._progress.get(time.time() * 1000)
        profile: Profile = self._profile.getProfile()
        reservation_bid = profile.getReservationBid()
        if reservation_bid is not None:
            return (self._isGoodLastBidBetterThanNext(bid) or (progress > .8 and self._isGoodAdjustingConstant(bid))) \
                   and profile.isPreferredOrEqual(profile.getReservationBid(), bid)
        else:
            return self._isGoodLastBidBetterThanNext(bid) or (progress > .8 and self._isGoodAdjustingConstant(bid))

    def _isGoodLastBidBetterThanNext(self, bid: Bid):
        """
        checks if the incoming bid is better than our next bid.
        """
        if bid is None:
            return False

        profile = self._profile.getProfile()
        utilityBid = profile.getUtility(bid)
        utilityNextBid = self._utility.get_last_own_bid_utility()
        return utilityBid > utilityNextBid

    def _isGoodAdjustingConstant(self, bid: Bid):
        """
        Checks if the bid is good when compared to an adjusting constant, like the max utility of all received bids.
        """
        if bid is None:
            return False
        profile = self._profile.getProfile()
        bidHistory, utilityHistory, bools = list(zip(*self._utility.get_bid_history()))
        alpha = max(0.7, max(utilityHistory))  # can also be exchanged for average, base alpha can also be adjusted

        return profile.getUtility(bid) > alpha


class BetterThanOwnAcceptanceStrategy(AbstractAcceptanceStrategy):
    """
    Not used acceptance strategy based on whether the received bid has a better utility than the last bid we offered.
    """

    def accept(self, bid: Bid):
        if bid is None:
            return False

        profile = self._profile.getProfile()
        progress = self._progress.get(time.time() * 1000)

        max_util = self._last_made_bid_utility if hasattr(self, "_last_made_bid_utility") else 1
        # very basic approach that accepts if the offer is valued above 0.6 and
        # 80% of the rounds towards the deadline have passed
        return profile.getUtility(bid) > max_util


class BetterThanEstimated(AbstractAcceptanceStrategy):
    """
    This is the acceptance strategy used, accepts a bid if the received bid offers a similar utility for both parties.
    The max difference allowed increases as the negotiation progresses in order to avoid losing a deal.
    """

    def __init__(self, fall_off_util=2, fall_off_difference=4, profile: Profile = None, progress: Progress = None,
                 utility: AgentUtility = None):
        super(BetterThanEstimated, self).__init__(profile, progress, utility)
        self.fall_off_util = fall_off_util
        self.fall_off_difference = fall_off_difference

    def accept(self, bid: Bid):
        """
        Acceptance method that will compare the estimated opponent utility and our received utility, from there it will decide
        to accept the bid based on the progress of the negotiation.
        """
        opponent_utility = self.get_utility(bid)
        own_utility = self._profile.getProfile().getUtility(bid).__float__()
        max_difference = (np.e ** -(1 - (self._progress.get(time.time() * 1000) ** 2))) / self.fall_off_difference

        reservation_bid = self._profile.getProfile().getReservationBid()
        if reservation_bid is not None:
            return (own_utility - opponent_utility) > -max_difference and (own_utility > (1 - max_difference * self.fall_off_util)) and \
                   self._profile.getProfile().isPreferredOrEqual(self._profile.getProfile().getReservationBid(), bid)

        else:
            return (own_utility - opponent_utility) > -max_difference and (own_utility > (1 - max_difference * self.fall_off_util))

    def get_utility(self, bid):
        """
        Method to retrieve the estimated utility of the opponent.
        """
        opponent_issue_percentage = self._utility.get_opponent_issue_count()
        opponent_issue_weights = self._utility.get_weight_heuristic()
        return self._utility.rate_bid(bid, opponent_issue_percentage, opponent_issue_weights)
