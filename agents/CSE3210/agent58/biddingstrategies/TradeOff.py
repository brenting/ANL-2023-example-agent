from decimal import Decimal
from random import randint
from typing import cast

from geniusweb.bidspace.AllBidsList import AllBidsList

from ..Constants import Constants


class TradeOff:
    def __init__(self, profile, opponent_model, offer, domain):
        self._profile = profile
        self._opponent_model = opponent_model
        self._offer = offer
        self._tolerance = Constants.iso_bids_tolerance
        self._domain = domain
        self._issues = domain.getIssues()
        self._sorted_bids = self._sort_bids(AllBidsList(self._domain))

    # sort bids on Utility descending
    def _sort_bids(self, all_bids):
        bids = []
        for b in all_bids:
            bid = {"bid": b, "utility": self._profile.getUtility(b)}
            bids.append(bid)
        return sorted(bids, key=lambda d: d['utility'], reverse=True)

    # return set of iso curve bids
    def _iso_bids(self, n=5):
        bids = []
        i = 0
        for bid in self._sorted_bids:
            if self._offer + self._tolerance > bid["utility"] > self._offer - self._tolerance:
                bids.append(bid["bid"])
                i += 1
            if i == n:
                break
        return bids

    # return a random bid
    def _get_random_bid(self):
        all_bids = AllBidsList(self._domain)
        return all_bids.get(randint(0, all_bids.size() - 1))

    # decrease our utility if we do not make any progress
    def _decrease_offer(self, received_bids, sent_bids, boulware):
        if len(sent_bids) > 3:
            utilLast = self._profile.getUtility(sent_bids[len(sent_bids) - 1])
            utilThreeStepsAgo = self._profile.getUtility(sent_bids[len(sent_bids) - 4])
            opponentUtilLast = self._profile.getUtility(received_bids[len(received_bids) - 1])
            opponentUtilOneStepAgo = self._profile.getUtility(received_bids[len(received_bids) - 2])
            if utilLast == utilThreeStepsAgo and opponentUtilLast <= opponentUtilOneStepAgo:
                self._offer = boulware

    # find a bid by using trade off strategy
    def find_bid(self, opponent_model, last_opponent_bid, received_bids, sent_bids, boulware):
        self._opponent_model = opponent_model

        self._decrease_offer(received_bids, sent_bids, boulware)

        # generate n bids
        bids = self._iso_bids()

        if last_opponent_bid is None:
            if len(bids) > 0:
                return bids[0]
            else:
                return self._get_random_bid()

        if len(bids) == 0:
            return self._get_random_bid()

        # choose bid with maximum utility for opponent
        best_bid = bids[0]
        max_util = 0
        for bid in bids:
            util = self._opponent_model.utility(bid)
            if util > max_util:
                best_bid = bid
                max_util = util

        return best_bid
