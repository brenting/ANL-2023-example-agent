import logging
import random
import time
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

from .MyOpponentModel import MyOpponentModel
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter


class Agent11(DefaultParty):
    """
    Template agent that offers random bids until a bid with sufficient utility is offered.
    """

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._last_received_bid = None

        self.sorted_bids = None
        self.opponent_model = None
        self.concede_range = 0.7
        self._second_to_last_received_bid = None
        self._last_offered_bid = None
        self._window_size = 20
        self._bias_correction = 0.015
        self.concede_count = 0
        self.non_concede_count = 0
        self.concede_strategy = 10
        self.received_bids = []
        # list that tries to keep track of the movement of the opponent bids
        self.opponent_delta = []

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
            self._profile = ProfileConnectionFactory.create(
                info.getProfile().getURI(), self.getReporter()
            )
            # initialize opponent model
            self.opponent_model = MyOpponentModel.create().With(self._profile.getProfile().getDomain(), None)
            # self.opponent_model = FrequencyOpponentModel.create().With(self._profile.getProfile().getDomain(), None)

        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()

            # if it is an offer, set the last received bid
            if isinstance(action, Offer) and action.getActor() != self._me:
                self._last_received_bid = cast(Offer, action).getBid()
                self.received_bids.append(self._last_received_bid)

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
        return "Agent11"

    # execute a turn
    def _myTurn(self):
        progress = self._progress.get(time.time() * 1000)
        # register bet with the opponent model
        if self._last_received_bid:
            self.opponent_model = self.opponent_model.WithAction(Offer(None, self._last_received_bid), progress)

        self._recognize_move()
        # Check if last received offer is good enough and more than 80% passed
        if self._isGood(self._last_received_bid):
            action = Accept(self._me, self._last_received_bid)
        else:
            # Opponents bid was not good enough, we make a bid.
            bid = self._findBid()

            self._secondToLast_offered_bid = self._last_offered_bid
            self._last_offered_bid = bid

            action = Offer(self._me, bid)

        return action

    def _isGood(self, bid: Bid) -> bool:
        """
        Checks if a bid is good enough to accept.
        @param bid the bid to consider
        @return true if the bid is good enough, false otherwise
        """
        if bid is None:
            return False

        utilities = self._calculate_utilities(bid, verbose=True)  # returns a tuple with (total, ours, theirs)
        utilities_prev_offered_bid = self._calculate_utilities(self._last_offered_bid)

        # We evaluate the following boolean conditions and base our final decision on them
        good_for_me = utilities[0] >= 0.6
        time_spend = self._progress.get(time.time() * 1000) >= 0.8
        better_than_last_offered = self._last_offered_bid and utilities_prev_offered_bid[0] <= utilities[0]
        better_than_reservation_value = self._profile.getProfile().getReservationBid() and self._profile \
            .getProfile().getReservationBid() <= good_for_me

        return ((good_for_me and time_spend) and better_than_reservation_value) or better_than_last_offered

    def _findBid(self) -> Bid:
        # compose a list of all possible bids
        domain = self._profile.getProfile().getDomain()
        all_bids = AllBidsList(domain)
        if not self.sorted_bids:
            self.sorted_bids = sorted(all_bids, key=lambda x: self._profile.getProfile().getUtility(x), reverse=True)

        if self._progress.get(time.time() * 1000) < self.concede_range:
            bid_index = random.randint(0, int(len(self.sorted_bids) * 0.005))

            bid = self.sorted_bids[bid_index]

            return bid
        else:
            delta = 0.1

            # Every x rounds, we sum the last x deltas to check what the opponents strategy is.
            # From experiments, an agent that concedes will get a score around -0.5 to -0.3
            # An agent that hard lines will get a score around 0 or bigger than 0
            # Against conceding agents, we will be more conservative and take on an hard lining strategy
            # Against hard lining agents, we will concede more.
            # A lower value of concede_strategy means we concede more
            # A higher value means we are more conservative
            if len(self.received_bids) % 10 == 0:
                opponent_trend = sum(self.opponent_delta[-10:])
                if opponent_trend < -0.2:
                    self.concede_strategy += 1
                else:
                    self.concede_strategy -= 1 if self._progress.get(time.time() * 1000) < 0.8 \
                        else 2  # start conceding more towards the end
                # we make sure this constant falls between a reasonable range, so it doesn't get too crazy
                self.concede_strategy = max(min(self.concede_strategy, 15), 3)
            # concede range = time after we concede
            start_index = int(
                len(self.sorted_bids) * (self._progress.get(time.time() * 1000) - self.concede_range) / self.concede_strategy)
            # start_index = 0
            # delta = randomness parameter for the generation of the bids
            end_index = int(len(self.sorted_bids) * (self._progress.get(time.time() * 1000) - self.concede_range + delta))

            bidding_range = self.sorted_bids[start_index:end_index]
            potential_bids = []
            # pick n random bids
            n = 50
            for _ in range(n):
                potential_bids.append(bidding_range[random.randint(0, len(bidding_range) - 1)])

            # find the best one according to ur best utility
            potential_bids = sorted(potential_bids,
                                    key=lambda x: self._evaluate_utilities(self._calculate_utilities(x)),
                                    reverse=True)
            bid = potential_bids[0]

            return bid

    def _calculate_utilities(self, bid: Bid, verbose=False):
        """
        Returns a tuple of the utility of an bid. The tuple consists of (total utility, own utility, opponent utility)
        """
        if not bid:
            return 0, 0
        own_utility = self._profile.getProfile().getUtility(bid)
        opponent_utility = self.opponent_model.getUtility(bid)
        if verbose:
            self.getReporter().log(logging.INFO,
                                   'Own utility ' + str(own_utility) + ' Opponent utility ' + str(opponent_utility))

        return own_utility, opponent_utility

    @staticmethod
    def _evaluate_utilities(utilities: tuple[float, float]) -> float:
        ratio = 0.6
        return ratio * float(utilities[0]) + (1-ratio) * float(utilities[1])

    def _recognize_move(self):
        """
        Evaluates the last x bids received where x is equal to the window size.
        It then calculates of this window was a conceding window or a non conceding window by calculating the delta
        It adds the delta to a list and this list will then be used to adjust our concession rate.
        """

        if len(self.received_bids) < self._window_size:
            return

        start = len(self.received_bids) - self._window_size
        half = len(self.received_bids) - int(self._window_size / 2)

        # function to map the bids to the estimated utility

        first_half = list(map(lambda x: self.opponent_model.getUtility(x), self.received_bids[start:half]))
        second_half = list(map(lambda x: self.opponent_model.getUtility(x), self.received_bids[half:]))

        # now we calculate the average utility
        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)

        # It takes into account that an opponent model will naturally be a little conceding over time
        # hence the bias correction
        delta = float(second_avg - first_avg) + self._bias_correction
        self.opponent_delta.append(delta)
