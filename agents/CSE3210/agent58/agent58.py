import logging
import time

from typing import cast

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)

from .Constants import Constants
from .acceptancestrategies.AcceptanceStrategy import AcceptanceStrategy
from .biddingstrategies.TradeOff import TradeOff
from .opponentmodels.OpponentModel import OpponentModel
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter


class Agent58(DefaultParty):
    """
    Template agent that offers random bids until a bid with sufficient utility is offered.
    """

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)

        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._last_received_bid = None
        self._received_bids = []
        self._sent_bids = []
        self.opponent_model = None
        self.offer = Constants.offer
        self.floor = Constants.floor
        self.boulware = self.offer
        self.bidding_strat = None
        self.acceptance_strat = None

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

            # BOA initializing
            self.opponent_model = OpponentModel(self._profile.getProfile().getDomain())
            # open('OpponentModel.log', 'w').close()
            self.bidding_strat = TradeOff(self._profile.getProfile(), self.opponent_model, self.offer,
                                          self._profile.getProfile().getDomain())
            self.acceptance_strat = AcceptanceStrategy(self._profile.getProfile(), self.floor,
                                                       self._profile.getProfile().getDomain())

        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()

            # if it is an offer, set the last received bid
            if isinstance(action, Offer) and action.getActor().getName() != self._me.getName():
                self._last_received_bid = cast(Offer, action).getBid()
                self._received_bids.append(self._last_received_bid)
                self.opponent_model.update_frequencies(self._last_received_bid)
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
        super().terminate()
        if self._profile is not None:
            self._profile.close()
            self._profile = None

    

    # give a description of your agent
    def getDescription(self) -> str:
        return "Trade-Off/TitForTat hyrbrid negotiation agent"

    # Generate a variable that follows a boulware curve
    def TimeDependent(self):
        if self._progress.get(time.time() * 1000) > Constants.boulware_time_limit and self.offer > Constants.floor:
            self.boulware = self.boulware - (Constants.boulware_conceding_speed * self._progress.get(time.time() * 1000))

    # execute a turn
    def _my_turn(self):
        self.TimeDependent()
        # generate a bid for the opponent
        bid = self.bidding_strat.find_bid(self.opponent_model, self._last_received_bid, self._received_bids,
                                          self._sent_bids, self.boulware)

        # check if opponents bid is better than ours, if yes then accept, else offer our bid
        if self.acceptance_strat.is_good(self._last_received_bid, bid, self._progress.get(time.time() * 1000)):
            return Accept(self._me, self._last_received_bid)
        else:
            # save expected utility for OM graph
            # with open("OpponentModel.log", "a") as text_file:
            #     text_file.write(str(self.opponent_model.utility(bid)) + "\n")

            self._sent_bids.append(bid)
            return Offer(self._me, bid)
