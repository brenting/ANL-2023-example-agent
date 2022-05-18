import logging
import time
import random
from random import randint, choices
from typing import cast

import geniusweb.opponentmodel.FrequencyOpponentModel as freq_opp_mod
import numpy as np
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
from geniusweb.progress.Progress import Progress
from .acceptance_strategy import AcceptanceStrategy
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter


# A custom agent that combines different strategies and changes between them based on time
# At first the agent enters an exploration phase where it acts as a very strict random walker
# After the exploration phase the agent starts behaving like the Agreeable agent, picking bids based on minimum
# utility and roulette selection based on social welfare
# After that, if the agents still did not find an agreement, the agent will start looking for the best nash product
# Lastly the agent will start sending bids that it already received, maximizing its utility
class Agent18(DefaultParty):
    """
    -- Shreker --
    The Shreker agent is an agent that changes its strategy depending on the time in the following order:
    - Random walker: initially explores opponent utility space while prevent opponent from getting our best bids
    - Agreeable: agent by Sahar Mirzayi from ANAC 2018; offers the highest utility bid that concedes on one issue
                 from the offer
    - Social welfare: late into the negotiation optimizes social welfare if opponent still has not conceded much
    - Received bids: very late into the negotiation return one of the best bids out of the 20 last received bids
    """

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        # Stores the last received bid
        self._last_received_bid: Bid = None
        # List of all received bids
        self._received_bids: list[Bid] = []
        # Stores the last sent bid
        self._last_sent_bid = None
        # Stores the best utility stored so far
        self._best_received_utility = 0.0
        # Stores all the thresholds used throughout the agent
        # 0 -> Threshold for acceptance strategy
        # 1 -> Threshold for random walker | RandomWalker
        # 2 -> Minimum target utility | Agreeable
        # 3 -> Factor of the time dependent utility | Agreeable
        # 4,5,6 -> Time splits for changing strategies
        self.thresholds: list[float] = [0.99, 0.980278280105376, 0.9586147509907781, 3.846489410609955,
                                    0.5702511194471804, 0.8702511194471804, 0.99]
        # Ranges for the thresholds for optimization purposes
        self.threshold_checks = [[0.8, 1], [0.7, 1], [0.7, 1], [2, 4],
                                 [0.3, 0.7], [0.7, 0.9], [0.9, 1]]

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

            self._bid_list = sorted(AllBidsList(self._profile.getProfile().getDomain()),
                                    key=self._profile.getProfile().getUtility, reverse=True)
            self._opponent_model = freq_opp_mod.FrequencyOpponentModel(self._profile.getProfile().getDomain(), {}, 0,
                                                                       None).With(
                self._profile.getProfile().getDomain(), None)
        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()

            # if it is an offer, set the last received bid
            if isinstance(action, Offer):
                bid = cast(Offer, action).getBid()
                if self._last_sent_bid is None or bid != self._last_sent_bid:
                    self._last_received_bid = bid
                    self._received_bids.append(self._last_received_bid)
                    self._opponent_model = self._opponent_model.WithAction(action, self._progress)
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
        return """
        -- Shreker --
        The Shreker agent is an agent that changes its strategy depending on the time in the following order:
        - Random walker: initially explores opponent utility space while prevent opponent from getting our best bids
        - Agreeable: agent by Sahar Mirzayi from ANAC 2018; offers the highest utility bid that concedes on one issue 
                     from the offer
        - Social welfare: late into the negotiation optimizes social welfare if opponent still has not conceded much
        - Received bids: very late into the negotiation return one of the best bids out of the 20 last received bids"""

    # execute a turn
    def _myTurn(self):
        # Update best received utility
        if self._last_received_bid is not None and self._best_received_utility < self._profile.getProfile().getUtility(
                self._last_received_bid):
            self._best_received_utility = self._profile.getProfile().getUtility(self._last_received_bid)
        # Find the next bid to send
        next_sent_bid = self._findBid()

        # Check whether the bid the bid to be offered follows some specific strategy based on received bids
        # We do pass a bid we create, it is not an error :)
        if self._isGood(next_sent_bid):
            # If the next bid we would send wouldn't improve our chances of getting a better outcome, accept the last
            # received bid
            action = Accept(self._me, self._last_received_bid)
        else:
            # Otherwise, sent the bid, remove it so we do not send the same bid over and over
            if next_sent_bid in self._bid_list:
                self._bid_list.remove(next_sent_bid)
            self._last_sent_bid = next_sent_bid
            action = Offer(self._me, next_sent_bid)

        # send the action
        return action

    # Method to check if we want to end the negotiation based on our next bid
    def _isGood(self, next_sent_bid) -> bool:
        if len(self._received_bids) == 0:
            return False
        profile = self._profile.getProfile()

        progress = self._progress.get(time.time() * 1000)

        # Create an acceptance profile and check the metrics used
        ac = AcceptanceStrategy(progress, profile, self._received_bids, next_sent_bid, self._last_sent_bid)
        return ac.combi_max_w(self.thresholds[0], 1, 0)

    # Finds the next bid to send to the opponent
    # Until threshold[4] -> RandomWalker
    # threshold[4] until threshold[5] -> AgreeableAgent
    # threshold[5] until threshold[6] -> SocialWelfareAgent
    # After threshold[7] -> Send bids we received with best utility
    def _findBid(self):
        progress = self._progress.get(time.time() * 1000)
        profile = self._profile.getProfile()
        opponent = self._opponent_model
        # Random Walker above specific threshold
        if progress < self.thresholds[4]:
            return self._generateRandomBidAbove(lambda x: x >= self.thresholds[1], self._bid_list, profile.getUtility)
        # Agreeable agent based on ANAC 2018 agent
        if progress < self.thresholds[5]:
            return self._agreeable()
        # Agent that maximizes the nash product
        if progress < self.thresholds[6]:
            return self._socialWelfare(lambda x: (self._profile.getProfile().getUtility(x)) * opponent.getUtility(x))
        # Send bids that we received and maximize our utility
        return self._sendReceived()

    # Function to generate a random bid using a specific thresholding function
    # threshold_function -> lambda function that returns a boolean used to filter bids
    # bid_list -> list of bids to chose from
    # utility_function -> lambda function that computes the utility of a bid
    def _generateRandomBidAbove(self, threshold_function, bid_list, utility_function):
        for _ in range(50):
            bid = self._getRandomBid(bid_list)
            if threshold_function(utility_function(bid)):
                return bid
        return self._bid_list[0]

    # Generate a random element of the input list
    def _getRandomBid(self, bid_list) -> Bid:
        return bid_list[randint(0, len(bid_list) - 1)]

    # Finds the next bid in the behaviour of the agreeable agent
    # - gets all bids above a specific time threshold
    # - selects one of them based on the social welfare (roulette selection)
    def _agreeable(self) -> Bid:
        # To collect enough data start by sending the best offers for us
        target_utility = min(self.thresholds[2], (1 - self._progress.get(time.time() * 1000)) * self.thresholds[3])
        profile = self._profile.getProfile()
        bids = []
        for bid in self._bid_list:
            if profile.getUtility(bid) > target_utility:
                bids.append(bid)
        bids = sorted(bids, key=self._opponent_model.getUtility, reverse=True)
        if len(bids) == 0:
            return self._bid_list[0]
        weights = np.array(
            [float(profile.getUtility(bid)) + float(self._opponent_model.getUtility(bid)) for bid in bids])
        return choices(bids, weights=weights / np.sum(weights))[0]

    # Picks one bid from the bid list that maximizes a specific metric
    def _socialWelfare(self, metric):
        best_bid = self._bid_list[0]
        for bid in self._bid_list:
            if metric(best_bid) < metric(bid):
                best_bid = bid
        return best_bid

    # Sends bid we have received while maximizing our utility gained from them
    # Used at the very end to get as much as we can from the negotiation
    def _sendReceived(self):
        # Get top 20 received bids and select randomly based on our utility
        profile = self._profile.getProfile()
        top_20 = sorted(self._received_bids, key=profile.getUtility, reverse=True)[:20]
        weights = np.array([float(profile.getUtility(bid)) for bid in top_20])
        return random.choices(top_20, k=1, weights=weights / np.sum(weights))[0]
