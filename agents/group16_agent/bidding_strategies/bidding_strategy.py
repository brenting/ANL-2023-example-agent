from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.bidspace.AllBidsList import AllBidsList
from time import time
from random import randint


class BiddingStrategy:

    def __init__(self, profile, progress, opponent_model):
        self._profile = profile
        self._progress = progress
        self._opponent_model = opponent_model
        self._threshold = 0.95
        self._delta = 0.05

    def _sort_bids(self):
        all_bids = AllBidsList(self._profile.getDomain())
        bids = []
        for b in all_bids:
            bid = {"bid": b, "utility": self._profile.getUtility(b)}
            bids.append(bid)
        return sorted(bids, key=lambda d: d['utility'], reverse=True)

    def _get_random_bid(self):
        all_bids = AllBidsList(self._profile.getDomain())
        return all_bids.get(randint(0, all_bids.size() - 1))

    def _generate_own_similar_bids(self, sorted_bids):
        "Gather more opportunities as time passes by"
        similar_bids = []
        progress = self._progress.get(time() * 1000)
        n = int(round(progress * 0.001))
        i = 0
        for bid in sorted_bids:
            if (self._threshold + self._delta) > bid["utility"] > (self._threshold - self._delta):
                similar_bids.append(bid["bid"])
                i += 1
            if i == n:
                break
        return similar_bids

    def _make_concession(self, received_bids, sent_bids):
        if len(sent_bids) > 1:
            sent_utility_1 = self._profile.getUtility(sent_bids[len(sent_bids) - 1])
            received_utility_1 = self._profile.getUtility(received_bids[len(received_bids) - 1])

            sent_utility_2 = self._profile.getUtility(sent_bids[len(sent_bids) - 2])
            received_utility_2 = self._profile.getUtility(received_bids[len(received_bids) - 2])

            if sent_utility_1 >= sent_utility_2 and received_utility_1 < received_utility_2:
                self._threshold -= 0.05

    def find_bid(self, last_opponent_bid, received_bids, sent_bids) -> Bid:
        # stuck with the algorithm - make concession
        self._make_concession(received_bids, sent_bids)

        # generate set of bids that maximise own utility
        sorted_bids = self._sort_bids()
        bids = self._generate_own_similar_bids(sorted_bids)

        # no opponent bid made so far -> we start negotiation
        if last_opponent_bid is None:
            if len(bids) > 0:
                return bids[0]
            else:
                return sorted_bids[0]

        # no bids found to maximise own utility
        if len(bids) == 0:
            return self._get_random_bid()

        # find bid that maximises opponent utility from our own selected bids
        best_bid = bids[0]
        max_util = 0
        for bid in bids :
            opponent_util = self._opponent_model.getUtility(bid)
            if opponent_util > max_util:
                best_bid = bid
                max_util = opponent_util

        return best_bid
