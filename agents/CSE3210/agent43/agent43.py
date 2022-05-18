import logging
import time
from random import randint
from typing import cast

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.bidspace.Interval import Interval
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Value import Value
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from decimal import Decimal
from decimal import Context
from typing import Dict, Optional
from geniusweb.progress.ProgressRounds import ProgressRounds
from geniusweb.bidspace.BidsWithUtility import BidsWithUtility
from .extended_util_space_group_43 import ExtendedUtilSpace
from .frequency_opponent_model_group_43 import FrequencyOpponentModel
from tudelft_utilities_logging.Reporter import Reporter



class Agent43(DefaultParty):
    """ Group 43's agent """

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._me: PartyId = None
        self._last_received_bid: Bid = None
        self._last_received_utility = 0
        self._highest_received_bid: Bid = None
        self._highest_received_utility = 0
        self._estimate_nash = 0
        self._bids_with_util : BidsWithUtility = None
        # self._progress: Progress = None
        self._util_space : LinearAdditive = None
        self._extended_space: ExtendedUtilSpace = None
        self._frequency_opponent_model : FrequencyOpponentModel = None
        self._tracker = []
        # self._our_utilities = None
        self._number_of_potential_bids = 0
        self._conceding_parameter = 0.1

    def notifyChange(self, info: Inform):
        """ This is the entry point of all interaction with your agent after is has been initialised.
        Args:
            info (Inform): Contains either a request for action or information.
        """
        # a Settings message is the first message that will be send to your
        # agent containing all the information about the negotiation session.
        if isinstance(info, Settings):
            self._initialize(info)

        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            self._actionDone(info)

        # YourTurn notifies you that it is your turn to act
        elif isinstance(info, YourTurn):
            action = self._myTurn()
            if isinstance(self._progress, ProgressRounds):
                self._progress = self._progress.advance()
            self.getConnection().send(action)

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(info, Finished):
            # terminate the agent MUST BE CALLED
            # print("OPPONENT MODEL ", self._frequency_opponent_model.toString())
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

    # Terminates the agent and its connections
    # leave it as it is for this competition
    def terminate(self):
        self.getReporter().log(logging.INFO, "party is terminating:")
        super().terminate()
        if self._profile is not None:
            self._profile.close()
            self._profile = None

    

    def _initialize(self, info: Settings):
        self._settings: Settings = cast(Settings, info)
        self._me = self._settings.getID()

        # Progress towards the deadline has to be tracked manually through the use of the Progress object
        self._progress: ProgressRounds = self._settings.getProgress()

        # The profile contains the preferences of the agent over the domain
        self._profile = ProfileConnectionFactory.create(
            info.getProfile().getURI(), self.getReporter()
        )

        # Create bids and opponent model
        self._bids_with_util = BidsWithUtility.create(cast(LinearAdditive, self._profile.getProfile()))
        opponent_model : Dict[str, Dict[Value, float]] = {}

        # Init issues and set values to 0.5 for all issues
        for issue in self._profile.getProfile().getDomain().getIssues():
            for_issue : Dict[Value, float] = {}
            for value in self._profile.getProfile().getDomain().getValues(issue):
                for_issue[value] = 0.5
            opponent_model[issue] = for_issue

        # Init Frequency opponent model
        self._frequency_opponent_model = FrequencyOpponentModel(self._profile.getProfile().getDomain(), opponent_model, 0, None)
        # self._frequency_opponent_model = FrequencyOpponentModel.create().With(self._profile.getProfile().getDomain(), None)

        ### PREVIOUS IMPLEMENTATION ###
        # Get bids and sort on utility
        # all_bids =  self._bids_with_util.getBids(Interval(Decimal(0), Decimal(1)))
        # self._number_of_potential_bids = all_bids.size()
        # bids_list = []
        # for i in range(self._number_of_potential_bids - 1):
        #     bids_list.append(all_bids.get(i))
        # bids_list.sort(key=self._profile.getProfile().getUtility)
        # self._our_utilities = bids_list

    def _actionDone(self, actionDone):
        action: Action = cast(ActionDone, actionDone).getAction()
        # If it is an offer, set the last received bid
        if isinstance(action, Offer):
            current_bid = cast(Offer, action).getBid()
            self._last_received_bid = current_bid

            # Update opponent's method
            if not action.getActor() == self._me:
                self._updateOpponentModel(action)

            # Update highest uility received so far by an opponent's offer
            if self._profile.getProfile().getUtility(cast(Offer, action).getBid()) > self._highest_received_utility:
                self._highest_received_utility = self._profile.getProfile().getUtility(cast(Offer, action).getBid())

            self._last_received_bid = cast(Offer, action).getBid()
        pass


    # Give a description of your agent
    def getDescription(self) -> str:
        return "Agent43"

    # Execute a turn
    def _myTurn(self):
        self._updateUtilSpace()
        progress_so_far = self._progress.get(time.time() * 1000)

        # Compute reservation value if it exists
        res_bid = self._profile.getProfile().getReservationBid()
        res_value_satisfied = True
        if res_bid is not None:
            reservation_value = self._profile.getProfile().getUtility(self._profile.getProfile().getReservationBid())
            res_value_satisfied = (self._profile.getProfile().getUtility(self._last_received_bid) > reservation_value)

        # Check if the last received offer of the opponent is good enough, and set window
        if progress_so_far > 0.5:
            r = 1 - progress_so_far
            percentage = (progress_so_far - r) / progress_so_far
            print (percentage)
            window = [1 * percentage, 1]

        # If almost nearing end accept everything above reservation value
        # This reservation value still needs to be added
        if progress_so_far > 0.99 and res_value_satisfied:
            action = Accept (self._me, self._last_received_bid)

        # After 50% of progress, accept if better offer then in previous window.
        elif progress_so_far > 0.5 and self._acceptance(window):
            action = Accept(self._me, self._last_received_bid)

        # First part, accept depending on utility
        elif progress_so_far > 0 and self._last_received_bid and self._acceptance_time():
            action = Accept(self._me, self._last_received_bid)

        # If not, find a bid to propose as counter offer
        else:
            bid = self._findBid()
            action = Offer(self._me, bid)

        # If we dont receive a bid
        if (self._last_received_bid != None):
            self._tracker.append(self._profile.getProfile().getUtility(self._last_received_bid))

        # Send the action
        return action

    # Accept offer if it satisfies both conditions
    def _acceptance_time(self):
        # percentage = 1 / self._progress.getTotalRounds() * (1 - self._progress.get(time.time() * 1000))
        percentage = pow(self._progress.get(time.time() * 1000), 1 / self._conceding_parameter)
        # bid_threshold = self._our_utilities[round((1 - percentage) * (len(self._our_utilities) - 1))]
        # threshold = self._profile.getProfile().getUtility(bid_threshold)
        util_received_last = self._profile.getProfile().getUtility(self._last_received_bid)
        return util_received_last >= percentage and (util_received_last >= self._highest_received_utility)

    # Construct the time window and compute acceptance condition
    def _acceptance(self, window) -> bool:
        length = len(self._tracker)
        lower = round(length * window[0])
        higher = round(length * window[1])
        utilitiesWindow = self._tracker[lower:higher]
        maxUtil = max(utilitiesWindow)
        util_recieved_last = self._profile.getProfile().getUtility(self._last_received_bid)
        self._progress.get(time.time() * 1000)

        # Acceptance condition next
        AC_next = (util_recieved_last > self._profile.getProfile().getUtility(self._findBid()))

        if util_recieved_last >= maxUtil and self._acceptance_time() and AC_next:
            return True
        else:
            return False

    # Update Utility space.
    def _updateUtilSpace(self) -> LinearAdditive:  # throws IOException
        newutilspace = self._profile.getProfile()
        if not newutilspace == self._util_space:
            self._util_space = cast(LinearAdditive, newutilspace)
            self._extended_space = ExtendedUtilSpace(self._util_space)
        return self._util_space

    # Find utility of a given offer
    def findUtility(self, bid):
        return self._profile.getProfile().getUtility(bid)

    # Update opponent model and derive some social welfare results
    def _updateOpponentModel(self, offer: Action):
        self._frequency_opponent_model = FrequencyOpponentModel.WithAction(self._frequency_opponent_model, offer, self._progress)
        self._last_received_utility = self.findUtility(self._last_received_bid)
        if self._progress.get(time.time() * 1000) > 0:
            area = Decimal(Context.multiply(Context(),
                                            self._frequency_opponent_model.getUtility(
                                                self._last_received_bid),
                                            self._last_received_utility))

            if area > self._estimate_nash:
                self._estimate_nash = area
                self._my_nash_utility = self._last_received_utility

    # Find a bid to offer
    def _findBid(self) -> Bid:
        total_range = self._bids_with_util.getRange()
        range_min = total_range.getMin()
        range_max = total_range.getMax()

        # get the bid that are within time-based percentile of the set range
        percentage = pow(self._progress.get(time.time() * 1000), 1 / self._conceding_parameter)
        percentile = Context.subtract(Context(), range_max, Context.multiply(Context(), Context.subtract(Context(), range_max, range_min), Decimal.from_float(0.1 + percentage)))
        range_of_bids = self._bids_with_util.getBids(Interval(percentile, range_max))

        # Using opponent model, filter out those bids that will not be highly valued by opponent.
        socialy_acceptably_bids = []
        for b in range_of_bids:
            if self._progress.get(time.time() * 1000) < 0.5:
                return range_of_bids.get(randint(0, range_of_bids.size() - 1))
            else:
                if self._frequency_opponent_model.getUtility(b) >= 0.5:
                    socialy_acceptably_bids.append(b)

        if len(socialy_acceptably_bids) < 1:
            return range_of_bids.get(randint(0, range_of_bids.size() - 1))

        # Once bids that do not yield a high social welfare are filtered out, select one randomly
        bid_chosen = socialy_acceptably_bids[randint(0, len(socialy_acceptably_bids) - 1)]
        return bid_chosen



