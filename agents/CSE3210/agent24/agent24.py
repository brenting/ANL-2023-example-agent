import decimal
import logging
import time
from random import randint
from typing import cast
import numpy as np

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value
from geniusweb.issuevalue.ValueSet import ValueSet
from geniusweb.opponentmodel import FrequencyOpponentModel
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter



class Agent24(DefaultParty):
    """
    Tit-for-tat agent that offers bids according to the opponents bids.
    """

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._last_received_bid: Bid = None
        self._opponent_model = FrequencyOpponentModel.FrequencyOpponentModel.create()
        self._issue_weights = []
        self._value_changed = []
        self._bids_matrix = []
        self._frequency_matrix = []
        self._previous_bid_enemy = 1
        self._previous_bid_self = 1

    def notifyChange(self, info: Inform):

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
        return "The ultimate Bastard tit-for-tat agent"

    # execute a turn
    def _myTurn(self):

        if self._last_received_bid is None:
            bid = self._findBid(1)
            action = Offer(self._me, bid)
        else:
            len_weights = len(self._last_received_bid.getIssues())
            dict_values = list(self._last_received_bid.getIssueValues().values())
            self._bids_matrix.append(dict_values)

            if len(self._issue_weights) == 0:
                for i in range(len_weights):
                    self._issue_weights.append(1 / len_weights)
                    self._value_changed.append(1)
                    self._frequency_matrix.append({dict_values[i]: 1})

            else:
                for i in range(len_weights):
                    last_bid = list(self._last_received_bid.getIssueValues().values())[i]
                    if self._bids_matrix[-1][i] != last_bid:
                        self._value_changed[i] *= 2
                    self._issue_weights[i] = (sum(self._value_changed) - self._value_changed[i]) / \
                                             (sum(self._value_changed) * (len_weights - 1))
                    if last_bid not in self._frequency_matrix[i]:
                        self._frequency_matrix[i][last_bid] = 1
                    else:
                        self._frequency_matrix[i][last_bid] += 1

            utility = 0
            for i in range(len_weights):
                utility += self._issue_weights[i] * (self._frequency_matrix[i][list(self._last_received_bid.getIssueValues().values())[i]] / sum(self._frequency_matrix[i].values()))

            bid = self._findBid(utility)
            if self._isOpponentBidGood(self._last_received_bid):
                action = Accept(self._me, self._last_received_bid)

            else:
                # if not, find a bid to propose as counter offer
                action = Offer(self._me, bid)

        # send the action
            self._previous_bid_enemy = utility
        return action

    # determine if bid should be accepted
    def _isOpponentBidGood(self, bid: Bid) -> bool:
        if bid is None:
            return False
        profile = self._profile.getProfile()
        progress = self._progress.get(time.time() * 1000)

        # set reservation value
        if self._profile.getProfile().getReservationBid() is None:
            reservation = 0.0
        else:
            reservation = profile.getUtility(self._profile.getProfile().getReservationBid())

        # ACconst
        if profile.getUtility(bid) >= 0.99:
            return True

        # boulware/conceder
        beta = 0.000000001  # beta: small = boulware, large = conceder, 0.5 = linear
        k = 0.9
        a = k + (1.0 - k) * pow(progress, (1.0 / beta))
        min1 = 0.8
        max1 = 1.0
        utility = min1 + (1.0 - a) * (max1 - min1)
        if profile.getUtility(bid) >= utility:
            return True

        return progress >= 0.99 and profile.getUtility(bid) > reservation

    def _findBid(self, utility) -> Bid:
        # compose a list of all possible bids
        changed_utility = self._previous_bid_enemy - utility

        domain = self._profile.getProfile().getDomain()
        profile = self._profile.getProfile()
        all_bids = AllBidsList(domain)

        found = False
        for _ in range(5000):
            bid = all_bids.get(randint(0, all_bids.size() - 1))
            if -0.2 < decimal.Decimal(self._previous_bid_self) - profile.getUtility(bid) - (decimal.Decimal(changed_utility) * decimal.Decimal(0.3)) < 0.05 and self._previous_bid_self - profile.getUtility(bid) < 0.1:
                found = True
                break
        if not found:
            for _ in range(5000):
                bid = all_bids.get(randint(0, all_bids.size() - 1))
                if self._previous_bid_self - profile.getUtility(bid) < 0.1:
                    break
        self._previous_bid_self = profile.getUtility(bid)
        return bid
