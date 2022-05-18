import logging
import time
from decimal import Decimal
from typing import cast

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.bidspace.BidsWithUtility import BidsWithUtility
from geniusweb.bidspace.Interval import Interval
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.opponentmodel.FrequencyOpponentModel import FrequencyOpponentModel
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter


class Agent14(DefaultParty):

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._last_received_bid = None
        self.last_my_utility = 1
        self.last_bids = []

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
            # initialize FrequencyOpponentModel
            self._opponent_model = FrequencyOpponentModel.create().With(
                newDomain=self._profile.getProfile().getDomain(),
                newResBid=self._profile.getProfile().getReservationBid())

            # sort all issues by relevance
            profile = self._profile.getProfile()
            issue_infos = BidsWithUtility._getInfo(profile, 6)
            weights = self._profile.getProfile().getWeights()
            issue_infos.sort(key=lambda x: weights[x.getName()])
            issue_infos.reverse()

            # initialize BidsWithUtility with sorted issues
            self._all_bids = BidsWithUtility(issue_infos, 6)

        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()

            # if it is an offer, set the last received bid
            if isinstance(action, Offer):
                self._last_received_bid = cast(Offer, action).getBid()

                if self._last_received_bid:
                    # Adjust FrequencyOpponentModel with new bid
                    self._opponent_model = self._opponent_model.WithAction(action=action, progress=self._progress)
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
        return "Group 14 Negotiation agent"

    # execute a turn
    def _myTurn(self):
        # check if the last received offer if the opponent is good enough
        if self._isGood(self._last_received_bid):
            # if so, accept the offer
            action = Accept(self._me, self._last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            bid = self._findBid()
            action = Offer(self._me, bid)

        # send the action
        return action

    # method that checks if we would agree with an offer.
    # our agent accepts the offer only if utility received is higher than
    # last utility calculated by _getNextUtility
    def _isGood(self, bid: Bid) -> bool:
        if bid is None:
            return False
        return self._profile.getProfile().getUtility(bid) >= self.last_my_utility

    # This calculates utility of the next bid agent should make
    # e in range [1, inf] - exponential coefficient
    # k in range [1, inf] - linear coefficient
    def _getNextUtility(self, e, k):
        util = 1 - self._progress.get(time.time() * 1000) ** e - 1/k * self._progress.get(time.time() * 1000)
        return util

    def _findBid(self) -> Bid:
        # Calculate next utility
        # Optimal values are k=4 and e=10
        utility = Decimal(self._getNextUtility(4, 10))
        eps = Decimal(0.01)

        # Looks for bids in BidsUtilitySpace in interval(utility-eps, utility+eps)
        # In case no bids found, extends interval
        best_bid = None
        while best_bid is None:
            bids_interval = self._all_bids.getBids(Interval(min=utility - eps, max=utility + eps))

            # Finds the maximum utility bid for the opponent in interval
            max_util = Decimal(0)
            for bid in bids_interval:
                # Making sure that bid was not proposed in last n turns
                # Optimal parameter for n is 5
                if bid not in self.last_bids[-5:]:
                    bid_util = self._opponent_model.getUtility(bid)
                    if bid_util >= max_util:
                        best_bid = bid
                        max_util = bid_util
            eps = eps + Decimal(0.01)

        self.last_my_utility = utility
        self.last_best_bid = best_bid
        self.last_bids.append(best_bid)
        return best_bid
