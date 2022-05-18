import logging
import time
from datetime import datetime, timedelta
from typing import cast

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
from geniusweb.opponentmodel.FrequencyOpponentModel import FrequencyOpponentModel
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profileconnection.ProfileConnectionFactory import (ProfileConnectionFactory)
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter


class Agent64(DefaultParty):
    """
    Template agent that offers random bids until a bid with sufficient utility is offered.
    """

    cur_max = 0.8
    cur_min = 0.0

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._last_received_bid: Bid = None
        self._last_received_action: Action = None
        self._opponent_model: FrequencyOpponentModel = None
        # Keeping track of best bid up until now for later usage
        self._best_bid: Bid = None
        self._lowest_bid: Bid = None
        self._all_received_offers = []
        self._past_20_offers = []
        self._opponent_concedes = False
        self._can_modify = True
        self.cmin = 0.95
        self.cmax = 1.0
        self.niceness = 0.00125
        self._concesssion_treshold = 1.2
        self.accept_offer_now_time = None

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
            self.accept_offer_now_time = self._progress.getTerminationTime() - timedelta(seconds=2)

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
                self._last_received_action = cast(Offer, action)
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
        return "Agnet64"

    # execute a turn
    def _myTurn(self):
        self._opponentModelling()

        # Store all received bids for acceptance purposes
        self._all_received_offers.append(self._last_received_bid)

        if self._last_received_bid is not None:
            # Store past 20 recieved bid utilities
            if (len(self._past_20_offers) < 20):
                self._past_20_offers.append(self._profile.getProfile().getUtility(self._last_received_bid))
            else:
                self._past_20_offers = self._past_20_offers[1:]

            if (self._profile.getProfile().getUtility(self._last_received_bid) / np.mean(
                    self._past_20_offers) > self._concesssion_treshold):
                self._opponent_concedes = True
            if (self._profile.getProfile().getUtility(self._last_received_bid) / np.mean(
                    self._past_20_offers) < self._concesssion_treshold):
                self._opponent_concedes = False
                self._can_modify = True

        profile = self._profile.getProfile()
        if self._best_bid is None or profile.getUtility(self._last_received_bid) > profile.getUtility(self._best_bid):
            self._best_bid = self._last_received_bid
        if self._lowest_bid is None or profile.getUtility(self._last_received_bid) < profile.getUtility(
                self._lowest_bid):
            self._lowest_bid = self._last_received_bid

        # Find an appropriate bid
        bid = self._findBid()
        # check if the last received offer if the opponent is good enough
        if self._last_received_bid is not None and self._accept(bid):
            # print("Utility of the accepted bid:  " + str(profile.getUtility(self._last_received_bid)))
            action = Accept(self._me, self._last_received_bid)
        else:
            # if not, propose a bid as counter offer
            action = Offer(self._me, bid)

        # send the action
        return action

    # method that checks if we would agree with an offer
    def _accept(self, bid: Bid) -> bool:
        # First move, no offer yet
        if bid is None:
            return False

        current_round = self._progress.get(time.time() * 1000)
        profile = self._profile.getProfile()
        current_offer = profile.getUtility(self._last_received_bid)
        own_bid_util = profile.getUtility(bid)

        # if near deadline
        if current_round >= 0.98: # or datetime.now() >= self.accept_offer_now_time:
            window = int((1 - current_round) * 200)
            bids = []
            for offer in self._all_received_offers[-window:]:
                if offer:
                    bids.append(profile.getUtility(offer) * self._opponent_model.getUtility(offer))

            # (This max method checks if the current offer is better than the all the offers in the window)
            if current_offer >= np.max(bids):
                # print("Current offer (" + (str(round(current_offer, 2))) + ") is better than the max ("
                #       + str(round(np.max(bids), 2)) + ") of the previous "
                #       + str(window) + " offers, accepting...")
                return True

        # C_next, checks if the offer we are about to make is equal or worse to the current offer from opponent
        # If so, a consensus has been achieved

        if current_offer >= own_bid_util:
            # print("About to offer something worse than what we were offered " + str(round(own_bid_util, 3))
            #       + ", accepting: " + str(round(current_offer, 3)))
            return True
        else:
            return False

    def _findBid(self) -> Bid:
        if self._opponent_concedes is False:
            self.cmin -= self.niceness
        if self._opponent_concedes is True and self._can_modify is True:

            if self.cmin <= 0.85:
                self.cmin += 0.05
            self._can_modify = False

        if self._progress.get(time.time() * 1000) > 0.2:
            bid = self.get_random_bid()
        else:
            bid = self.get_true_random_bid()
        if self._progress.get(time.time() * 1000) >= 0.995:
            bid = self._best_bid

        return bid

    def get_random_bid(self):
        available_bids = AllBidsList(self._profile.getProfile().getDomain())
        random_better_bids = [bid for bid in available_bids if
                              self.cmin <= self._profile.getProfile().getUtility(bid) <= self.cmax]
        if len(random_better_bids) == 0:
            random_better_bids = [
                max(map(lambda bid: (bid, self._profile.getProfile().getUtility(bid)), available_bids),
                    key=lambda tup: tup[1])[0]]
            return random_better_bids[0]
        best_bid_for_opponent = [
            max(map(
                lambda bid: (bid, self._opponent_model.getUtility(bid) * self._profile.getProfile().getUtility(bid)),
                random_better_bids),
                key=lambda tup: tup[1])[0]]
        return best_bid_for_opponent[0]

    def get_true_random_bid(self):
        available_bids = AllBidsList(self._profile.getProfile().getDomain())
        random_better_bids = [bid for bid in available_bids if self._profile.getProfile().getUtility(bid) >= self.cmin]
        if len(random_better_bids) == 0:
            random_better_bids = [
                max(map(lambda bid: (bid, self._profile.getProfile().getUtility(bid)), available_bids),
                    key=lambda tup: tup[1])[0]]
        return np.random.choice(random_better_bids)

    def _opponentModelling(self):
        if self._opponent_model is None:
            self._createFrequencyOpponentModelling()
        self._opponent_model = self._opponent_model.WithAction(self._last_received_action, self._progress)

    def _createFrequencyOpponentModelling(self):
        domain = self._profile.getProfile().getDomain()
        self._opponent_model: FrequencyOpponentModel = FrequencyOpponentModel.create().With(domain, newResBid=None)
