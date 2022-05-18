import logging
import time
from typing import cast
from operator import itemgetter
import numpy as np
from decimal import Decimal

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
from .FreqModelWeighted import FreqModelWeighted
from tudelft_utilities_logging.Reporter import Reporter

"""
BeanBot agent
"""
class Agent52(DefaultParty):

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._last_received_bid: Bid = None
        self._last_received_action = None
        self._opp_model = None
        self._window_size = 10 # last 10 opponent bids are stored window below
        self._opp_bids_window = []
        self._opp_best_bid = None

    def notifyChange(self, info: Inform):
        """This is the entry point of all interaction with your agent after is has been initialised.

        Args:
            info (Inform): Contains either a request for action or information.
        """

        # a Settings message is the first message that will be send to your
        # agent containing all the information about the negotiation session.
        if isinstance(info, Settings):
            self._settings: Settings = cast(Settings, info)
            self._me = self._settings.getID()

            # progress towards the deadline has to be tracked manually through the use of the Progress object
            self._progress: ProgressRounds = self._settings.getProgress()

            # the profile contains the preferences of the agent over the domain
            self._profile = ProfileConnectionFactory.create(
                info.getProfile().getURI(), self.getReporter()
            )

            # Create the weighted frequency model
            self._opp_model = FreqModelWeighted.create().With(self._profile.getProfile().getDomain(), None)
            self._opp_model.__class__ = FreqModelWeighted


            # Generate sorted (decr.) list of all possible bids with their corresponding utility values
            # Create reservation value after
            profile = self._profile.getProfile()
            allBids = AllBidsList(self._profile.getProfile().getDomain())
            self._bid_utility_tuple = [(bid, profile.getUtility(bid)) for bid in allBids]
            self._bid_utility_tuple.sort(key=itemgetter(1), reverse=True)

            # set reservation value to maximum of (0.4, worst bid utility in domain)
            alpha = 0.4
            self._rsv_val = alpha if alpha > self._bid_utility_tuple[-1][1] else self._bid_utility_tuple[-1][1]

        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()

            # if it is an offer, set the last received bid
            if isinstance(action, Offer):
                self._last_received_bid = cast(Offer, action).getBid()
                self._last_received_action = action
        # YourTurn notifies you that it is your turn to act
        elif isinstance(info, YourTurn):
            action = self._myTurn()
            if isinstance(self._progress, ProgressRounds):
                self._progress = self._progress.advance()
            self.getConnection().send(action)

        # Finished will be send if the negotiation has ended (through agreement or deadline)
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
        return "BeanBot implementation for Collaborative AI course"

    # execute a turn
    def _myTurn(self):
        # Update the frequency model and the issue weights with the last received bid
        self._opp_model = self._opp_model.WithAction(self._last_received_action, self._progress)
        self._opp_model.__class__ = FreqModelWeighted
        self._opp_model.updateIssueWeights()

        # Update the best bid offered by the opponent if the last received bid is better for us
        profile = self._profile.getProfile()
        self._opp_best_bid = self._last_received_bid \
            if self._opp_best_bid is None or profile.getUtility(self._last_received_bid) > profile.getUtility(self._opp_best_bid) \
            else self._opp_best_bid

        # Update the bids in the window of last received bids (window has size self._window_size)
        if self._last_received_bid is not None:
            self._opp_bids_window.append(profile.getUtility(self._last_received_bid))
        if len(self._opp_bids_window) > self._window_size:
            self._opp_bids_window.pop(0)

        bid = self._findBid()
        action = Offer(self._me, bid)
        # AC_combi check whether we should accept current offer or not
        if self._isGood(self._last_received_bid, bid):
            action = Accept(self._me, self._last_received_bid)

        # send the action
        return action


    """
    AC_combi hybrid acceptance strategy.
    Uses AC_next condition in the first [0, T) fraction of the negotiation.
    Additionally accepts some form of best opponent offer in phase [T, 1] of the negotiation (end phase).
    This can be either if the received utility is better than overall best received bid, best bid in window,
        or average utility in window.
    """
    def _isGood(self, offeredBid: Bid, nextBid: Bid, T=0.9) -> bool:
        if offeredBid is None:
            return False

        # progress represents fraction of negotiation that has passed
        profile = self._profile.getProfile()
        progress = self._progress.get(time.time() * 1000)

        # AC_next or AC_combi if we are in phase [T, 1]
        accept = profile.getUtility(offeredBid) > profile.getUtility(nextBid) \
                 or (progress > T and self._window_max())
        return accept

    """
    The following three methods represent the three possible AC_combi methods described above.
    """
    def _window_max(self):
        # check if better than maximum utility in past window
        profile = self._profile.getProfile()
        return profile.getUtility(self._last_received_bid) >= np.max(self._opp_bids_window)

    def _window_avg(self):
        # check if better than average utility in past window
        profile = self._profile.getProfile()
        return profile.getUtility(self._last_received_bid) >= np.mean(self._opp_bids_window)

    def _overall_max(self):
        # check if better than maximum utility received in entire negotiation
        profile = self._profile.getProfile()
        return profile.getUtility(self._last_received_bid) >= profile.getUtility(self._opp_best_bid)

    """
    Implements bidding strategy inspired by the AgreeableAgent2018 (ANAC2018).
    Take all bids higher than target utility and pick random one based on opponent preferences to send to opponent.
    """
    def _findBid(self) -> Bid:
        # e value determines concession rate by influencing the shape of the target utility curve
        e = 0.3
        max_util = self._bid_utility_tuple[0][1]
        target_util = self._getUtilityGoal(self._progress.get(time.time() * 1000), e, Decimal(self._rsv_val), max_util)
        # Allow for some additional (10% of target utility) randomness in the possible bids to send to opponent
        # in the first half of the negotiation. Otherwise, will send mostly the same bid constantly at first.
        if self._progress.get(time.time() * 1000) < 0.5:
            target_util = target_util - Decimal(np.random.uniform(0, 0.1 * float(target_util)))

        candidates = []
        opp_utilities = []
        # Find all bids above target utility and store along with the associated opponent utilities of the bids
        for items in self._bid_utility_tuple:
            if items[1] < target_util:
                break
            candidates.append(items[0])
            opp_utilities.append(float(self._opp_model.getUtility(items[0])))

        # apply roulette wheel selection to the bids to choose one using exponential fitness function
        return self._roulette_selection(candidates, opp_utilities, self._fitness_exp)

    """
    Roulette wheel selection to select a random bid to send.
    Scale opponent utilities to [0, 1], apply fitness function to it and use fitness values as probabilities 
        for choosing each bid.
    """
    def _roulette_selection(self, candidates, utilities, fitness_func, eps=0.0001):
        normalised_utils = np.array(utilities)

        # if same utilities, choose random bid, otherwise continue scaling to [0, 1]
        if np.max(normalised_utils) - np.min(normalised_utils) < eps:
            return np.random.choice(candidates)

        # scale utilities to [0, 1]
        normalised_utils = (normalised_utils - np.min(normalised_utils)) / (np.max(normalised_utils) - np.min(normalised_utils))
        # apply fitness function and divide by total sum in order to obtain probability values for each bid
        fitnesses = fitness_func(normalised_utils)
        fitnesses /= np.sum(fitnesses)
        # return random bid using fitnesses as weights, or completely random bid if something went wrong in fitnesses
        return np.random.choice(candidates, p=fitnesses) if not np.isnan(fitnesses).any() else np.random.choice(candidates)

    """
    Next two functions allow for two different shapes for the fitness transformation of the utilities
    """
    def _fitness_linear(self, normalised_utils):
        return 0.3 + 0.7 * normalised_utils

    def _fitness_exp(self, normalised_utils, alpha=3):
        return np.exp(-alpha*(1-normalised_utils))

    """
    Same function as used by time_dependent_agent to determine the curve of utility target line.
    """
    def _getUtilityGoal(
        self, t: float, e: float, minUtil: Decimal, maxUtil: Decimal
    ) -> Decimal:
        """
        @param t       the time in [0,1] where 0 means start of nego and 1 the
                       end of nego (absolute time/round limit)
        @param e       the e value that determinses how fast the party makes
                       concessions with time. Typically around 1. 0 means no
                       concession, 1 linear concession, &gt;1 faster than linear
                       concession.
        @param minUtil the minimum utility possible in our profile
        @param maxUtil the maximum utility possible in our profile
        @return the utility goal for this time and e value
        """

        ft1 = Decimal(1)
        if e != 0:
            ft1 = round(Decimal(1 - pow(t, 1 / e)), 6)  # defaults ROUND_HALF_UP
        return max(min((minUtil + (maxUtil - minUtil) * ft1), maxUtil), minUtil)
