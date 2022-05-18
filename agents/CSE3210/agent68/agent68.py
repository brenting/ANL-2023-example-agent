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
from geniusweb.issuevalue.Bid import Bid
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressRounds import ProgressRounds
from geniusweb.opponentmodel.FrequencyOpponentModel import FrequencyOpponentModel
from tudelft_utilities_logging.Reporter import Reporter

# from main.bidding.bidding import Bidding
# from Group68_NegotiationAssignment_Agent.bidding.bidding import Bidding
from .bidding.bidding import Bidding

from time import time as clock


class Agent68(DefaultParty):
    """
    Template agent that offers random bids until a bid with sufficient utility is offered.
    """
    PHASE_ONE_ROUNDS = (0, 10)  # Reconnaissance
    PHASE_TWO_ROUNDS = (11, 70)  # Main negotiation

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self._progress = None
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._last_received_bid: Bid = None

        # New attributes
        self._opponent = FrequencyOpponentModel.create()
        self._freqDict = {}
        self._bidding: Bidding = Bidding()
        self._selfCurrBid: Bid = None

        self._e1 = 0.3
        self._e2 = 0.3
        self._e3 = 0.1
        
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

            self._opponent = self._opponent.With(self._profile.getProfile().getDomain(), None)

            self._getParams()
            self._bidding.initBidding(cast(Settings, info), self.getReporter())

        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()

            # if it is an offer, set the last received bid
            if isinstance(action, Offer):

                offer: Offer = cast(Offer, action)
                # print(self._profile.getProfile().getReservationBid())
                if offer.getActor() != self._settings.getID():
                    opp_bid = cast(Offer, action).getBid()
                    self._last_received_bid = opp_bid
                    self._opponent = self._opponent.WithAction(action, self._progress)
                    self._bidding.updateOpponentUtility(self._opponent.getUtility)
                    opponent_utility = self._opponent.getUtility(opp_bid)
                    # print("Estimated opponent utility: " + str(opponent_utility))
                    self._bidding.receivedBid(opp_bid)

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
        self._updateRound(info)

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

        super().terminate()
        if self._profile is not None:
            self._profile.close()
            self._profile = None

    

    def _getParams(self):
        params = self._settings.getParameters()
        
        self._e1 = params.getDouble("e1", 0.3, 0.0, 2.0)
        self._e2 = params.getDouble("e2", 0.3, 0.0, 2.0)
        self._e3 = params.getDouble("e3", 0.1, 0.0, 2.0)
        
        
    
    def _updateRound(self, info: Inform):
        """
        Update {@link #progress}, depending on the protocol and last received
        {@link Inform}

        @param info the received info.
        """
        if self._settings == None:  # not yet initialized
            return

        if not isinstance(info, YourTurn):
            return

        # if we get here, round must be increased.
        if isinstance(self._progress, ProgressRounds):
            self._progress = self._progress.advance()
            self._bidding.updateProgress(self._progress)

    # give a description of your agent
    def getDescription(self) -> str:
        return "Agent68"

    # execute a turn
    def _myTurn(self):
        self._bidding._updateUtilSpace()
        self._progress.get(round(clock() * 1000))
        # check if the last received offer if the opponent is good enough
        #TODO try changing params and integrating with acceptance strat. Try filtered combinations
        if self._progress.get(round(clock() * 1000)) < 0.4:
            self._bidding.setE(self._e1)
        elif self._progress.get(round(clock() * 1000)) < 0.8:
            self._bidding.setE(self._e2)
        else:
            self._bidding.setE(self._e3)
        if self._bidding._isGood(self._last_received_bid):
            # if so, accept the offer
            action = Accept(self._me, self._last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            bid = self._bidding.makeBid(self._opponent)
            action = Offer(self._me, bid)
            opponent_utility = self._opponent.getUtility(bid)

        # send the actionp
        return action

