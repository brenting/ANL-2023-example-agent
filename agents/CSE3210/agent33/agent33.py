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
from geniusweb.progress.Progress import Progress

from .acceptance_strategy import CombiAcceptanceStrategy, BetterThanEstimated
from .utility import AgentUtility
from .bidding_strategy import BiddingStrategyProbalistic, BiddingStrategyDeterministic, \
    AgressiveBiddingStrategy
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter


class TemplateAgent(DefaultParty):
    """
    Template agent that offers random bids until a bid with sufficient utility is offered.
    """

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None

        self._utility = AgentUtility()
        self._strategy = AgressiveBiddingStrategy(utility=self._utility)
        self._acceptance = CombiAcceptanceStrategy(utility=self._utility)

        self._last_received_bid = None

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
            self._progress: Progress = self._settings.getProgress()

            # the profile contains the preferences of the agent over the domain
            self._profile = ProfileConnectionFactory.create(
                info.getProfile().getURI(), self.getReporter()
            )

            self._strategy.set_profile(self._profile)
            self._utility.set_profile(self._profile)
            self._acceptance.set_profile(self._profile)

            self._acceptance.set_progress(self._progress)
            self._utility.set_progress(self._progress)




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
            self._utility.set_progress(self._progress)
            self._acceptance.set_progress(self._progress)
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
            {"SAOP"},
            {"geniusweb.profile.utilityspace.LinearAdditive"},
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
        return "Agent33"

    # execute a turn
    def _myTurn(self):
        if self._last_received_bid is not None:
            # add opponent bid to bid history
            self._utility.append_to_bid_history(self._last_received_bid, False)
            self._utility.update_opponent_weight_heuristic(self._last_received_bid)
            self._utility.update_opponent_issue_count(self._last_received_bid)

        # check if the last received offer if the opponent is good enough
        if self._isGood(self._last_received_bid):
            # if so, accept the offer
            action = Accept(self._me, self._last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            bid = self._findBid()
            action = Offer(self._me, bid)
            # add bid to our bid history
            self._utility.append_to_bid_history(bid, True)

        # send the action
        return action

    def _isGood(self,
                bid: Bid) -> bool:  # adjust acceptance criteria based on how many turns left, accept if last bid is better than our next bid
        if bid is None:
            return False
        return self._acceptance.accept(bid)

    def _findBid(self) -> Bid:
        return self._strategy.get_bid()


class DeterministicAgent(TemplateAgent):

    def __init__(self):
        super(DeterministicAgent, self).__init__()
        self._strategy = BiddingStrategyDeterministic(utility=self._utility)


class ProbabilisticAgent(TemplateAgent):

    def __init__(self):
        super(ProbabilisticAgent, self).__init__()
        self._strategy = BiddingStrategyProbalistic(utility=self._utility)


class AgressiveAtStartAgent(TemplateAgent):

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self._strategy = AgressiveBiddingStrategy(utility=self._utility)
        self._acceptance = CombiAcceptanceStrategy(utility=self._utility)
        self.ratings = 0
        self.switched = False

    def _myTurn(self):
        self._updateStrategy()
        return super(AgressiveAtStartAgent, self)._myTurn()


    def _updateStrategy(self):
        if not self.switched:
            opponent_issue_percentage = self._utility.get_opponent_issue_count()
            opponent_issue_weights = self._utility.get_weight_heuristic()
            if self._last_received_bid is not None:
                rating = self._utility.rate_bid(self._last_received_bid, opponent_issue_percentage, opponent_issue_weights)
                if rating > 0.9:
                    self.ratings = 0
                else:
                    self.ratings += 1

            if self.ratings == 3 and self._progress.get(time.time() * 1000) > 0.25:
                self._strategy = BiddingStrategyDeterministic(utility=self._utility, profile=self._profile)
                self.switched = True
        else:
            opponent_issue_percentage = self._utility.get_opponent_issue_count()
            opponent_issue_weights = self._utility.get_weight_heuristic()
            if self._last_received_bid is not None:
                rating = self._utility.rate_bid(self._last_received_bid, opponent_issue_percentage, opponent_issue_weights)
                if rating > 0.9:
                    self.ratings += 1
                else:
                    self.ratings = 0

            if self.ratings == 3:
                self._strategy = BiddingStrategyDeterministic(utility=self._utility, profile=self._profile)

class AgressiveAtStartWithOpponentAcceptance(AgressiveAtStartAgent):

    def __init__(self):
        super(AgressiveAtStartWithOpponentAcceptance, self).__init__()
        self._acceptance = BetterThanEstimated(fall_off_util=1, fall_off_difference=2, utility=self._utility)


class Agent33(AgressiveAtStartAgent):

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self._strategy = AgressiveBiddingStrategy(utility=self._utility)
        self._acceptance = BetterThanEstimated(fall_off_util=1, fall_off_difference=2, utility=self._utility)


    def _findBid(self) -> Bid:
        bid = self._strategy.get_bid()
        if not self._isGood(bid):
            self._strategy = BiddingStrategyProbalistic(utility=self._utility, profile=self._profile)
            return self._findBid()
        return bid