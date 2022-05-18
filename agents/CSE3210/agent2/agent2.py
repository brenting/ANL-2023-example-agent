from decimal import Decimal
import logging
import math
from random import randint
import time
from typing import Callable, cast
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive

from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList
from ...time_dependent_agent.extended_util_space import ExtendedUtilSpace

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
from geniusweb.profile.Profile import Profile
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.profileconnection.ProfileInterface import ProfileInterface
from .group2_frequency_analyzer import FrequencyAnalyzer
from .group2_plot_trace import plot_characteristics
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter


class Agent2(DefaultParty):
    """
    Template agent that offers random bids until a bid with sufficient utility is offered.
    """

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profileint: ProfileInterface = None # type:ignore
        self._last_received_bid: Bid = None # type:ignore
        self._utilspace: UtilitySpace = None # type:ignore
        self._extendedspace: ExtendedUtilSpace = None # type:ignore

        self.highest_social_welfare_bid: list[Bid] = []

        # General settings
        self.opponent_model = FrequencyAnalyzer()
        self.reservation_utility: float = .0 # not sure if this is a good value to have, since any agreement is better than no agreement...
        self.concession_speed: float = 11.0 # higher will concede slower (1/e is approximately linear) [0.0, ...]
        self.attempts: int = 500 # the number of iterations it will go through to look for an 'optimal' bid
        self.hard_to_get: float = .2 #  the moment from which we'll consider playing nice [0.0, 1.0]
        self.niceness: Decimal = Decimal(.05) # utility we're considering to give up for the sake of being nice [0.0, 1.0]

        # Agent characteristics:
        # Can be included in plotting, make sure the dimensionality of all of them match up
        self.lower_utility_bound: list[float] = []
        self.our_social_welfare: list[float] = []
        self.their_social_welfare: list[float] = []
        self.their_social_welfare: list[float] = []
        self.esitmated_opponent_utility: list[float] = []

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
            self._progress = self._settings.getProgress()

            # the profile contains the preferences of the agent over the domain
            self._profileint = ProfileConnectionFactory.create(
                info.getProfile().getURI(), self.getReporter()
            )
            self.opponent_model.set_domain(self._profileint.getProfile().getDomain())

            reservation_bid = self._profileint.getProfile().getReservationBid()

            if reservation_bid is not None:
                profile, _ = self._get_profile_and_progress()
                self.reservation_utility = profile.getUtility(reservation_bid)

        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()

            # if it is an offer, set the last received bid
            if isinstance(action, Offer):
                self._last_received_bid = cast(Offer, action).getBid()
        # YourTurn notifies you that it is your turn to act
        elif isinstance(info, YourTurn):
            action = self._my_turn()
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
        # self._plot_characteristics()
        super().terminate()
        if self._profileint is not None:
            self._profileint.close()

    # ===================
    # === AGENT LOGIC ===
    # ===================

    # give a description of your agent
    def getDescription(self) -> str:
        return "Shaken, not stirred"

    # execute a turn
    def _my_turn(self):
        self._update_utilspace()
        self.opponent_model.add_bid(self._last_received_bid)

        next_bid = self._find_bid(self.attempts)

        if self._is_acceptable(self._last_received_bid, next_bid):
            action = Accept(self._me, self._last_received_bid)
        else:
            action = Offer(self._me, next_bid)

        # send the action
        return action

    # =================
    # === ACCEPTING ===
    # =================

    def _is_acceptable(self, bid: Bid, our_next_bid: Bid) -> bool:
        if bid is None:
            return False

        profile, _ = self._get_profile_and_progress()
        bid_utility = profile.getUtility(bid)

        threshold = self._lower_util_bound()

        self.lower_utility_bound.append(threshold)
        self.our_social_welfare.append(float(self._social_welfare(our_next_bid)))
        self.their_social_welfare.append(float(self._social_welfare(bid)))
        self.esitmated_opponent_utility.append(float(self.opponent_model.get_utility(our_next_bid)))

        # has to be higher than the reservation value and our threshold, but if the bid is better than we expect we'll always accept
        return (bid_utility > self.reservation_utility and bid_utility > threshold) or bid_utility > profile.getUtility(our_next_bid)

    def _lower_util_bound(self) -> float:
        _, progress = self._get_profile_and_progress()

        threshold = self._exponential_decrease(progress, self.concession_speed)

        return threshold

    """
    A function which is 1.0 at x=0.0, and 0.0 at x=1.0.
    k determines how quickly it falls to 0.0; higher k is slower decrease
    - k > 1/e will first fall slowly, then fast
    - k < 1/e will first fall fast, then slow
    - k = 1/e ~ linear
    Rounding errors make x=1.0 not actually intersect (worse with higher k),
    intersection with zero can be forced by setting force_intersect
    """
    def _exponential_decrease(self, x, k, force_intersect=True):
        if force_intersect and x > 0.99:
            return 0.0

        return -math.exp(x**k) + 2 - x**k * (-math.e + 2)

    # ===============
    # === BIDDING ===
    # ===============

    def _find_bid(self, attempts) -> Bid:
        # compose a list of all possible bids
        _, progress = self._get_profile_and_progress()

        # it the beginning we'll play hard to get
        # after that we'll consider playing nice
        # => this makes us indicate our interests and gives us
        #    the opportunity to collect information about our opponent
        if progress < self.hard_to_get:
            return self._find_max_bid()
        else:
            return self._find_max_nice_bid(attempts)

    """
    Gets a random bid from the given list of all_bids
    """
    def _get_random_bid(self, all_bids: ImmutableList[Bid]):
        return all_bids.get(randint(0, all_bids.size() - 1))

    """
    Finds the maximum bid according to a certain proposition
    """
    def _find_bid_with(self, proposition: Callable[[Bid, Bid], bool], attempts: int):
        # compose a list of all possible bids
        # TODO Make the selection more constrained, the frequency analyzer performs relatively well
        #      but the amount of time it takes to find a good/nice bid can be reduced significantly
        all_bids = AllBidsList(self._profileint.getProfile().getDomain())

        # TODO Also consider doing this differently
        maxBid = self._find_lower_bid()

        if maxBid is None:
            if len(self.highest_social_welfare_bid) == 0:
                maxBid = self._find_max_bid()
            else:
                maxBid = self.highest_social_welfare_bid[-1]

        for _ in range(attempts):
            bid = self._get_random_bid(all_bids)
            maxBid = bid if proposition(bid, maxBid) else maxBid

        self.highest_social_welfare_bid.append(maxBid)
        return maxBid

    """
    Find a bid according to the current lower bound
    returns _find_max_bid if no bid in that range can be found
    """
    def _find_lower_bid(self):
        lower_bound_bids = self._extendedspace.getBids(min(Decimal(self._lower_util_bound()), Decimal(1) - self.niceness))

        if lower_bound_bids.size() == 0:
            return None

        return self._get_random_bid(lower_bound_bids)

    """
    Find the maximum bids from the domain
    """
    def _find_max_bid(self) -> Bid:
        max_bids = self._extendedspace.getBids(self._extendedspace.getMax())
        return self._get_random_bid(max_bids)

    """
    Finds the maximum bid while trying to also accomodate the opponents interests
    according to _is_better_bid with be_nice set to True
    """
    def _find_max_nice_bid(self, attempts) -> Bid:
        # some cheeky CPL currying
        return self._find_bid_with((lambda a, b: self._is_better_bid(a, b,  self.niceness, be_nice=True) and self._is_acceptable(a, b)), attempts)

    """
    Checks if bid a is better than bid b.
    If be_nice is True, will also consider the opponents utility according to opponent_model and
    is willing to sacrifice a niceness amount of utility when comparing in order to create a win-win
    """
    def _is_better_bid(self, a: Bid, b: Bid, niceness: Decimal, be_nice=False) -> bool:
        profile, _ = self._get_profile_and_progress()

        if not be_nice:
            return profile.getUtility(a) >= profile.getUtility(b)
        else:
            # TODO look into niceness possibly accumulating over multiple self.attempts
            # TODO Social welfare metric?
            return profile.getUtility(a) >= profile.getUtility(b) - - niceness \
                and self.opponent_model.get_utility(a) >= self.opponent_model.get_utility(b)

    def _social_welfare(self, bid: Bid) -> Decimal:
        profile, _ = self._get_profile_and_progress()

        return (profile.getUtility(bid) + Decimal(self.opponent_model.get_utility(bid)))/Decimal(2.0)

    # ==============
    # === UTILS ====
    # ==============

    def _get_profile_and_progress(self) -> tuple[LinearAdditive, float]:
        profile: Profile = self._profileint.getProfile()
        progress: float = self._progress.get(time.time() * 1000)

        return cast(LinearAdditive, profile), progress

    def _update_utilspace(self) -> None:  # throws IOException
        newutilspace = self._profileint.getProfile()
        if not newutilspace == self._utilspace:
            self._utilspace = cast(LinearAdditive, newutilspace)
            self._extendedspace = ExtendedUtilSpace(self._utilspace)

    # ===================
    # === DEBUG TOOLS ===
    # ===================

    def _print_utility(self, bid: Bid) -> None:
        profile, _ = self._get_profile_and_progress()
        print("Bid:", bid, "with utility:", profile.getUtility(bid))

    def _plot_characteristics(self) -> None:
        characteristics = {
            "lowest acceptable utility": self._plot_space(self.lower_utility_bound, "gray"),
            "social welfare (ours, estimation)": self._plot_space(self.our_social_welfare, "green"),
            "social welfare (theirs, estimation)": self._plot_space(self.their_social_welfare, "blue"),
            "opponent utility (estimation)": self._plot_space(self.esitmated_opponent_utility, "red")
        }
        plot_characteristics(characteristics, len(self.lower_utility_bound))

    def _plot_space(self, arr: list, color: str) -> tuple[list, list, str]:
        return (list(range(len(arr))), arr, color)
