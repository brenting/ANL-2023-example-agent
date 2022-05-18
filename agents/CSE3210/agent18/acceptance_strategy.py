import decimal

import numpy as np


class AcceptanceStrategy:
    """
    Contains acceptance strategies that agents can use. According to "Acceptance Conditions in Automated Negotiation"
    (https://homepages.cwi.nl/~baarslag/pub/Acceptance_conditions_in_automated_negotiation.pdf) the following are the
    best strategies ranked according the average utility for the agent:
    1. combi_max_w
    2. combi_avg_w
    3. gap(0.1)
    4. combi_max_t
    5. time(0.99)
    6. gap(0.2)
    7. gap(0.05)
    8. next(1.02, 0)
    9. gap(0.02)
    10. prev(1.02, 0)
    11. next(1, 0)
    12. prev(1, 0)
    """

    def __init__(self, progress, profile, rec_bid_hist=None, next_sent_bid=None, prev_sent_bid=None):
        """
        Constructs an acceptance strategy object.
        @param progress: the current negotiation progress from 0 to 1 (essentially time).
        @param rec_bid_hist: the history of all the opponent's bids so far.
        """
        self.progress = progress
        self.profile = profile
        if rec_bid_hist and len(rec_bid_hist) == 0:
            Exception(f"Expected history of at least 1 bid but got 0")
        elif rec_bid_hist:
            self.rec_utility_hist = list(map(lambda bid: self.profile.getUtility(bid), rec_bid_hist))
            self.rec_bid_hist = rec_bid_hist
            self.last_rec_bid = rec_bid_hist[-1]
        self.next_sent_bid = next_sent_bid
        self.prev_sent_bid = prev_sent_bid

    def combi_max_w(self, progress_thresh, scale, const):
        """Combined strategy that checks a window of previously received bids"""
        window = self._get_bid_window()
        if len(window) != 0:
            # Take the maximum of the bid window
            alpha = np.max(window)
        else:
            alpha = 0
        return self._combi(progress_thresh, alpha, scale, const)

    def combi_avg_w(self, progress_thresh, scale, const):
        """Combined strategy that checks a window of previously received bids"""
        window = self._get_bid_window()
        if len(window) != 0:
            alpha = np.mean(window)
        else:
            alpha = 0
        return self._combi(progress_thresh, alpha, scale, const)

    def combi_max_t(self, progress_thresh, scale, const):
        """Combined strategy that checks all previously received bids"""
        alpha = np.max(self.rec_utility_hist)
        return self._combi(progress_thresh, alpha, scale, const)

    def _get_bid_window(self):
        if self.progress == 0:
            self.max_bids = 100
        else:
            # automatically figure out how many max bids there will be
            self.max_bids = len(self.rec_utility_hist) // self.progress
        num_bids = int(self.max_bids * self.progress)
        remaining_bids = int(self.max_bids * (1 - self.progress))
        # compute bounds of the bid window
        bounds = np.clip([num_bids - remaining_bids, num_bids], 0, len(self.rec_utility_hist) - 1)
        # print(bounds)
        if bounds[1] < bounds[0]:
            raise Exception("Invalid bounds")
        return self.rec_utility_hist[bounds[0]: bounds[1]]

    def _combi(self, progress_thresh, alpha, scale, const):
        """Helper method for the combi acceptance strategy. According to research most effective with T = 0.99."""
        early = self.next(scale, const)
        late = self.time(progress_thresh) and self.profile.getUtility(self.last_rec_bid) >= alpha
        # print(early, late)
        return early or late

    def gap(self, gap):
        return self.prev(1, gap)

    def time(self, progress_thresh):
        """Accepts bids after a certain time period"""
        return self.progress >= progress_thresh

    def next(self, scale_factor, utility_gap):
        """Accepts bids better the next bids that should be sent"""
        # print(f"|| Next sent for agent {hash(self.profile)}: {self.profile.getUtility(self.next_sent_bid)}")
        return decimal.Decimal(scale_factor) * self.profile.getUtility(self.last_rec_bid) \
               + decimal.Decimal(utility_gap) >= self.profile.getUtility(self.next_sent_bid)

    def prev(self, scale_factor, utility_gap):
        """Accepts bids better than the previous bid that has been sent"""
        return decimal.Decimal(scale_factor) * self.profile.getUtility(self.last_rec_bid) \
               + decimal.Decimal(utility_gap) >= self.profile.getUtility(self.prev_sent_bid)

    def const(self, utility_thresh):
        """Accepts bids over a utility threshold"""
        return self.profile.getUtility(self.last_rec_bid) > utility_thresh

    def IAMHaggler(self):
        return self.const(0.88) and self.next(1.02, 0) and self.prev(1.02, 0)
