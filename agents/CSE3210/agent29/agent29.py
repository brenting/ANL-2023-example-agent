import logging
import time
from decimal import Decimal

import numpy as np
from random import randint
from typing import cast

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter


class Agent29(DefaultParty):
    """
    Agent Hope

                Linear concession is used for target utilities.

                Each time a bid is to be chosen, a whole range of bids close to the target utility is considered from
                which, the ones with values closest to the estimated opponent's preferred values are prioritised for
                the final offer.

                Close to the deadline, the agent offers the bid with the highest utility from the set of all the bids
                received.

                Bids are accepted only if the are sufficiently better than the average received bid.
                This approach only accepts very good bids and only becomes more lenient towards the very end of
                negotiation.

                It is ensured that no bid with utility lower than the agent's reservation value
                is ever offered or accepted.
    """

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._last_received_bid = None
        self._reservation_value = 0.0
        self._all_opponent_bids: list[Bid] = []
        self._all_offered_bids: list[Bid] = []
        self._log_times = [np.log(i / 200) for i in range(1, 201)]
        self._log_times.insert(0, 0)
        self._e = 1.0
        self._last_ten_bids_counts = {}
        self._all_possible_bids: AllBidsList
        self._all_possible_bids_utils = []
        self._all_possible_bids_ord: list[Bid] = []
        self._all_possible_bids_ord_utils = []
        self._num_possible_bids = 0

    def notifyChange(self, info: Inform):
        """This is the entry point of all interaction with your agent after is has been initialised.

        Args:
            info (Inform): Contains either a request for action or information.
        """

        # a Settings message is the first message that will be sent to your
        # agent containing all the information about the negotiation session.
        if isinstance(info, Settings):
            self._settings: Settings = cast(Settings, info)
            self._me = self._settings.getID()

            # progress towards the deadline has to be tracked manually through the use of the Progress object
            self._progress = self._settings.getProgress()

            # the profile contains the preferences of the agent over the domain
            self._profile = ProfileConnectionFactory.create(
                info.getProfile().getURI(), self.getReporter()
            )

            # initialises the histogram opponent modelling
            self.initialise_bid_counts()
            self.initialise_all_possible_bids()
            self.initialise_reservation_value()
        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()

            # if it is an offer, set the last received bid
            if isinstance(action, Offer):
                self._last_received_bid = cast(Offer, action).getBid()
        # YourTurn notifies you that it is your turn to act
        elif isinstance(info, YourTurn):
            action = self._myTurn()
            if isinstance(self._progress, ProgressRounds):
                self._progress = self._progress.advance()
            self.getConnection().send(action)

        # Finished will be sent if the negotiation has ended (through agreement or deadline)
        elif isinstance(info, Finished):
            # terminate the agent MUST BE CALLED
            self.terminate()
        else:
            self.getReporter().log(
                logging.WARNING, "Ignoring unknown info " + str(info)
            )

    # lets the geniusweb system know what settings this agent can handle
    # leave it as it is for this competition
    def getCapabilities(self) -> Capabilities:
        return Capabilities(
            set(["SAOP"]),
            set(["geniusweb.profile.utilityspace.LinearAdditive"]),
        )

    # terminates the agent and its connections
    # leave it as it is for this competition
    def terminate(self):
        self.getReporter().log(logging.INFO, "party is terminating:")
        super().terminate()
        if self._profile is not None:
            self._profile.close()
            self._profile = None

    

    # give a description of your agent
    def getDescription(self) -> str:
        return "Agent Hope: Linear concession is used for target utilities. \nEach time a bid is to be chosen, " \
               "a whole range of bids close to the target utility is considered from which, the ones with values " \
               "closest to the estimated opponent's preferred values are prioritised for the final offer. \nClose to " \
               "the deadline, the agent offers the bid with the highest utility from the set of all the bids " \
               "received. \nBids are accepted only if the are sufficiently better than the average received bid. " \
               "This approach only accepts very good bids and only becomes more lenient towards the very end of " \
               "negotiation. \nIt is ensured that no bid with utility lower than the agent's reservation value " \
               "is ever offered or accepted."

    """
    Execute a turn
    """

    def _myTurn(self):
        if self._last_received_bid is not None:
            self._all_opponent_bids.append(self._last_received_bid)
        if len(self._all_opponent_bids) != 0:
            if len(self._all_opponent_bids) > 10:
                self._uncount_oldest_bid()
            self._count_last_bid()
        # check if the last received offer of the opponent is good enough
        if self._isGood(self._last_received_bid):
            # if so, accept the offer
            action = Accept(self._me, self._last_received_bid)
        # checks if the negotiation is nearing the end. If so, the best received offer is sent
        elif self._progress.get(time.time() * 1000) >= 0.95:
            opp_bids_utilities = [self._profile.getProfile().getUtility(bid) for bid in self._all_opponent_bids]
            best_opponent_bid = self._all_opponent_bids[np.argmax(opp_bids_utilities)]
            if self._profile.getProfile().getUtility(best_opponent_bid) >= self._reservation_value:
                action = Offer(self._me, best_opponent_bid)
            else:
                action = Offer(self._me, self._findBid())
        else:
            # if there is still time and the received offer was not good enough, the agent looks for a better one
            bid = self._findBid()
            action = Offer(self._me, bid)
            self._all_offered_bids.append(bid)

        # send the action
        return action

    """
    The method that finds a bid in multiple possible ways based on the current situation.
    If the opponent model is initialised, it uses it, otherwise a random bid is taken.
    """

    def _findBid(self) -> Bid:
        # find bids with utilities closest to the target utility
        target_utility = Decimal(1.0 - 0.3 * self._progress.get(time.time() * 1000))
        bids_to_consider = self.bids_close_to_target_util(target_utility)
        # only keep bids with utility above reservation value
        acceptable_bids = self.remove_bids_below_reservation(bids_to_consider)

        if len(acceptable_bids) == 0:  # if no bids are acceptable, offer one with util >= reservation
            best_bid = self.find_first_acceptable_bid()
        elif len(self._all_opponent_bids) >= 10:  # if the histogram is initialised, use it
            best_bid = self.best_domain_bid(acceptable_bids)
        else:  # if the histogram is not initialised, offer random bids
            # initialize the bid to something above reservation value
            best_bid = self.find_first_acceptable_bid()
            best_bid_util = self._profile.getProfile().getUtility(best_bid)

            # take attempts at finding a random bid that is acceptable to us
            best_bid = self.find_random_acceptable_bid(best_bid, best_bid_util)

        return best_bid

    """
    This method receives bids and checks whether they should be accepted. It is responsible for checking 
    the quality of bids the agent offers using a three stage approach depending on the progress (number of rounds 
    finished). 

    In the first stage, it refuses any bids, which gives the agent enough time to learn about the opponent 
    (establish the average and start domain modeling). 

    The second stage covers majority of the rounds and accepts offers only when the bid offered is significantly 
    better than average. 

    In the last stage if an agreement hasn't been reached yet, any bid is accepted as long as it is better than the 
    reservation_value.
    """

    def _isGood(self, bid: Bid) -> bool:
        if bid is None:
            return False

        # first stage - establish average of opponent
        if self._progress.get(time.time() * 1000) < 0.2:
            return False

        # second stage - check if the received bid improved by at least 50% above the average
        if self._progress.get(time.time() * 1000) < 0.97:
            return self._significantImprovement(bid, 0.5)

        # last part - this only gets executed if opponent doesn't accept an offer they sent previously.
        return self._profile.getProfile().getUtility(bid) > self._reservation_value

    """
    Check whether the offered bid has a utility greater than 0.8 (as well as greater than our reservation value)
    Not elaborate, only used for the first 10 offered bids (opponent acceptance at this stage is not really expected)
    """

    def _isGoodDomainAgent(self, bid: Bid) -> bool:
        if bid is None:
            return False
        bid_util = self._profile.getProfile().getUtility(bid)
        return bid_util > 0.8 and bid_util > self._reservation_value

    """
    Following method checks whether a given bid is better than an average bid by at least the value specified
    (significance). 

    It also checks whether the bid is better than the reservationBid (if specified).
    """

    def _significantImprovement(self, bid: Bid, significance: float) -> bool:
        if len(self._all_opponent_bids) == 0:
            return False

        # numpy average computation
        get_util = lambda x: float(self._profile.getProfile().getUtility(x))
        vgu = np.vectorize(get_util)
        average = np.average(vgu(self._all_opponent_bids))

        return float(self._profile.getProfile().getUtility(bid)) > average + significance and \
               float(self._profile.getProfile().getUtility(bid)) > self._reservation_value

    """
    Initializes an empty histogram for use in the domain modeling. 
    """

    def initialise_bid_counts(self):
        domain = self._profile.getProfile().getDomain()
        domain_issues = domain.getIssues()

        self._num_possible_bids = 1
        for issue in domain_issues:
            self._last_ten_bids_counts[issue] = {}
            issue_values = domain.getValues(issue)
            self._num_possible_bids *= issue_values.size()
            for issue_value in issue_values:
                self._last_ten_bids_counts[issue][issue_value] = 0

    """
    Initializes a list of bids in the agent's bid space, and sorts them as well. 
    """

    def initialise_all_possible_bids(self):
        domain = self._profile.getProfile().getDomain()
        self._all_possible_bids = AllBidsList(domain)
        for i in range(self._all_possible_bids.size()):
            current_bid = self._all_possible_bids.get(i)
            self._all_possible_bids_utils.append(self._profile.getProfile().getUtility(current_bid))
        self._all_possible_bids_utils = np.array(self._all_possible_bids_utils)
        sort_indices = np.argsort(self._all_possible_bids_utils)
        for i in range(self._all_possible_bids.size()):
            self._all_possible_bids_ord.append(self._all_possible_bids.get(sort_indices[i]))

        self._all_possible_bids_ord_utils = self._all_possible_bids_utils[sort_indices]
        self._all_possible_bids_ord_utils = self._all_possible_bids_ord_utils = \
            self._all_possible_bids_ord_utils.astype('float')

    """
    Initializes a reservation value, if a Reservation Bid is defined in the profile. 
    """

    def initialise_reservation_value(self):
        reservation_bid = self._profile.getProfile().getReservationBid()
        if reservation_bid is not None:
            self._reservation_value = self._profile.getProfile().getUtility(reservation_bid)

    """
    If the last received bid is not empty, add it to the histogram
    """

    def _count_last_bid(self):
        domain = self._profile.getProfile().getDomain()
        domain_issues = domain.getIssues()

        for issue in domain_issues:
            opponent_bid = self._last_received_bid
            opp_bid_value = opponent_bid.getValue(issue)
            if opp_bid_value is not None:  # measure against the stupid agent
                self._last_ten_bids_counts[issue][opp_bid_value] += 1

    """
    Remove the 11th most recent (i.e. the no longer relevant) bid from the histogram
    """

    def _uncount_oldest_bid(self):
        domain = self._profile.getProfile().getDomain()
        domain_issues = domain.getIssues()

        for issue in domain_issues:
            oldest_relevant_opp_bid = self._all_opponent_bids[-10]
            opp_bid_value = oldest_relevant_opp_bid.getValue(issue)
            self._last_ten_bids_counts[issue][opp_bid_value] -= 1

    """
    Return a number between 0 and 1 indicating how close the given bid is to the current opponent preference model.
    """

    def domain_similarity(self, bid: Bid):
        domain = self._profile.getProfile().getDomain()
        domain_issues = domain.getIssues()
        num_issues = len(domain_issues)

        similarity = 0.

        for issue in domain_issues:
            opp_bid_value = bid.getValue(issue)
            similarity += (self._last_ten_bids_counts[issue][opp_bid_value] / 10.0) / num_issues

        return similarity

    """
    Sort the given bids by how close they are to our opponent's preference model (histograms).
    """

    def sort_bids_by_similarity(self, bids_to_consider) -> list[Bid]:
        bid_similarities = []
        for i in bids_to_consider:
            bid_similarities.append(self.domain_similarity(i))

        bid_similarities_sort_index = np.argsort(bid_similarities)[::-1]
        sorted_bids = np.array(bids_to_consider)[bid_similarities_sort_index]

        return sorted_bids

    """
    Iterates over the array of bids sorted by similarity and tries to pick the first that hasn't been offered yet.
    If all bids from the list were already offered, the first bid is returned.
    """

    def choose_bid_high_similarity(self, sorted_bids):
        i = 0
        chosen_bid = sorted_bids[i]
        while chosen_bid in self._all_offered_bids and i < len(sorted_bids):
            chosen_bid = sorted_bids[i]
            i += 1
        if i == len(self._all_offered_bids):
            chosen_bid = sorted_bids[0]
        return chosen_bid

    """
    Choose a bid randomly with priority given to those with highest similarity.
    The choice happens through roulette wheel selection with exponential probabilities (1/2, 1/4, 1/8, ...)
    """

    def choose_bid_weighted_random(self, sorted_bids):
        probabilities = [1 / 2 ** (i + 1) for i in range(len(sorted_bids))]
        probabilities[-1] = probabilities[-2]

        cum_prob = np.cumsum(probabilities)
        rnd_n = np.random.uniform()

        chosen_bid = None
        for i in range(len(cum_prob)):
            if rnd_n < cum_prob[i]:
                chosen_bid = sorted_bids[i]
                break
        return chosen_bid

    """
    From the given list, choose a bid with priority given to bids with high similarity to the opponent model.
    Roughly 80% of bids will be chosen deterministically with choose_bid_high_similarity, the remaining 20% are chosen
    randomly with roulette wheel selection. 
    """

    def best_domain_bid(self, bids_to_consider) -> Bid:
        sorted_bids = self.sort_bids_by_similarity(bids_to_consider)

        choice_n = np.random.uniform()
        exploration_constant = 0.8
        if len(sorted_bids) == 1:  # when only one bid is considered, return it
            chosen_bid = sorted_bids[0]
        elif choice_n < exploration_constant:  # choose the bids with the highest similarity
            chosen_bid = self.choose_bid_high_similarity(sorted_bids)
        else:  # choose a bid with weighted randomness
            chosen_bid = self.choose_bid_weighted_random(sorted_bids)

        return chosen_bid

    """
    From all possible bids, extract those that are close to the target utility.
    2 * fraction * 100% bids are expected to be extracted, but it can be less when the target utility is very high
    (not enough bids with higher utility) or very low (not enough bids with lower utility)
    """

    def bids_close_to_target_util(self, target_utility, fraction=0.025):
        util_distances = np.abs(np.subtract(self._all_possible_bids_ord_utils, float(target_utility)))
        closest_bid_index = np.argmin(util_distances)
        radius = int(fraction * self._num_possible_bids)  # number of bids to consider
        bids_to_consider = self._all_possible_bids_ord[max(0, closest_bid_index - radius):
                                                       min(len(self._all_possible_bids_ord) - 1,
                                                           closest_bid_index + radius)]
        return bids_to_consider

    """
    From the given list of bids, remove all those that cannot be offered because of utility below reservation value.
    """

    def remove_bids_below_reservation(self, bids_to_consider):
        acceptable_bids = []
        for i in range(len(bids_to_consider)):
            if self._profile.getProfile().getUtility(bids_to_consider[i]) >= self._reservation_value:
                acceptable_bids.append(bids_to_consider[i])
        return acceptable_bids

    """
    From all possible bids, choose the one with lowest utility that is higher than the reservation value.
    """

    def find_first_acceptable_bid(self):
        best_bid = None
        for i in range(len(self._all_possible_bids_ord)):
            if self._all_possible_bids_ord_utils[i] >= self._reservation_value:
                best_bid = self._all_possible_bids_ord[i]
                break
        return best_bid

    """
    Make a fixed number of attempts at finding a random bid that would be acceptable.
    """

    def find_random_acceptable_bid(self, best_bid, best_bid_util, attempts=100):
        for _ in range(attempts):
            bid = self._all_possible_bids.get(randint(0, self._all_possible_bids.size() - 1))
            if self._isGoodDomainAgent(bid):  # if the bid is good, offer it
                best_bid = bid
                break
            # if the bid is not good but better than the best so far, update it
            if self._profile.getProfile().getUtility(bid) > best_bid_util:
                best_bid = bid
                best_bid_util = self._profile.getProfile().getUtility(bid)
        return best_bid
