from abc import abstractmethod
import numpy as np
from typing import List, Union

from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.issuevalue.Bid import Bid
from geniusweb.profileconnection.ProfileInterface import ProfileInterface

from .utility import AgentUtility


class AbstractBiddingStrategy:

    def __init__(self, profile: ProfileInterface = None, utility: AgentUtility = None):
        self._profile: ProfileInterface = profile
        self._utility: AgentUtility = utility

    def set_profile(self, profile: ProfileInterface):
        """Setter for profile interface"""
        self._profile: ProfileInterface = profile

    def set_utility(self, utility: AgentUtility):
        """Setter for utility interface"""
        self._utility: AgentUtility = utility


    @abstractmethod
    def get_bid(self) -> Bid:
        """Method for getting the next bid to make"""
        pass


class BiddingStrategyDeterministic(AbstractBiddingStrategy):

    def __init__(self, profile=None, utility=None):
        super().__init__(profile, utility)
        self._last_made_bid_utility = None
        if profile is not None:
            self.bids = self.most_to_least_likely()
        else:
            self.bids = []

    def set_profile(self, profile):
        """Setter for profile interface, intializes bids list"""
        self._profile = profile
        self.bids = self.most_to_least_likely()

    def get_bid(self):
        """This strategy determines the rating for a set of bids and returns the bid with the highest expected opponent utility"""
        possible_bids = []
        for i in range(self._utility.speed_factor()):
            possible_bids.append(self.bids.pop())
        else:
            possible_bids.append(self.bids.pop())

        distribution = self.get_bid_distribution(possible_bids)
        bid = possible_bids[distribution.index(max(distribution))]
        self._last_made_bid_utility = bid[1]
        return bid[0]


    def get_bid_distribution(self, bids):
        """Method """
        opponent_issue_percentage = self._utility.get_opponent_issue_count()
        opponent_issue_weights = self._utility.get_weight_heuristic()

        distribution: List[float] = []
        for bid in bids:
            distribution.append(self._utility.rate_bid(bid[0], opponent_issue_percentage, opponent_issue_weights))

        total_rating: float = sum(distribution)
        total_rating: Union[float, int] = total_rating if total_rating != 0 else 1
        normalized_distribution: List[float] = list(map(lambda x: x / total_rating, distribution))

        # if normalized distribution is 0 for all entries, return a uniform distribution instead
        if sum(normalized_distribution) == 0:
            normalized_distribution = list(map(lambda x: 1 / len(normalized_distribution), normalized_distribution))

        return normalized_distribution

    def most_to_least_likely(self):
        """
        method for generating the most to least profitable bids in order
        """
        domain = self._profile.getProfile().getDomain()
        all_bids = AllBidsList(domain)
        bids_values = []
        for bid in all_bids:
            bids_values.append((bid, self._profile.getProfile().getUtility(bid)))
        bids_values.sort(reverse=False, key=lambda x: x[1])
        return bids_values

    def getIssueUtilities(self, issue, issue_values):
        utility_values = []
        for iv in issue_values:
            bid = Bid({issue: iv})
            utility_values.append(self._profile.getProfile().getUtility(bid))
        return utility_values


class BiddingStrategyProbalistic(BiddingStrategyDeterministic):

    def __init__(self, profile=None, utility=None):
        super().__init__(profile, utility)


    def get_bid(self):
        possible_bids = []
        for i in range(self._utility.speed_factor()):
            possible_bids.append(self.bids.pop())
        else:
            possible_bids.append(self.bids.pop())

        distribution = self.get_bid_distribution(possible_bids)
        bid = possible_bids[np.random.choice(len(possible_bids), p=distribution)]
        self._last_made_bid_utility = bid[1]
        return bid[0]


class AgressiveBiddingStrategy(AbstractBiddingStrategy):
    def __init__(self, profile=None, utility=None):
        super().__init__(profile, utility)
        self.bids = []

    def get_bid(self) -> Bid:
        if len(self.bids) == 0:
            self.bids = self.get_all_bids_higher_than(0.8)

        bid = self.bids[np.random.choice(len(self.bids))]
        self.bids.remove(bid)

        return bid[0]

    def get_all_bids_higher_than(self, value: float) -> list:
        domain = self._profile.getProfile().getDomain()
        all_bids = AllBidsList(domain)
        bids_values = []
        for bid in all_bids:
            bids_values.append((bid, self._profile.getProfile().getUtility(bid)))
        bids_values.sort(reverse=False, key=lambda x: x[1])
        return list(filter(lambda bid: bid[1] > value, bids_values))
