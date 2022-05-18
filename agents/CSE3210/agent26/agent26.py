import random
import time
from ast import Dict
from decimal import Decimal
import logging
import profile
from random import randint, shuffle
import string
from typing import cast

import geniusweb
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
from geniusweb.issuevalue.Value import Value
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty


from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
import datetime
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter


class Agent26(DefaultParty):

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._last_received_bid: Bid = None
        self.offers_received: Dict[(str, Value), Decimal] = {}
        self._beta = 0.05
        self._accept = 1
        self._most_similar: Bid = None
        self._reservation = 0.3
        self._range = 0.05
        self._full_time = 0
        self._round_times: list[Decimal] = []
        self._last_time = None
        self._avg_time = None

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
            self._full_time = self._progress.getTerminationTime().timestamp() - datetime.datetime.now().timestamp()

            # the profile contains the preferences of the agent over the domain
            self._profile = ProfileConnectionFactory.create(
                info.getProfile().getURI(), self.getReporter()
            )
            if self._profile.getProfile().getReservationBid() is not None:
                self._reservation = self._profile.getProfile().getReservationBid()

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
        return "Giver agent for Collaborative AI course"

    # execute a turn
    def _myTurn(self):

        # Calculate minimum utility we accept using time dependent formula
        self._accept = self.get_time_dependent_utility(self._progress.get(time.time() * 1000), 1, self._beta, 1, self._reservation)

        # Creates and updates the Issue Value pair frequency dictionary for opponent modeling
        if self._last_received_bid is not None:
            for issue in self._last_received_bid.getIssues():
                if (issue, self._last_received_bid.getValue(issue)) in self.offers_received:
                    self.offers_received[(issue, self._last_received_bid.getValue(issue))] += 1
                else:
                    self.offers_received[(issue, self._last_received_bid.getValue(issue))] = 1

        # For calculating average time per round
        if self._last_time is not None:
            self._round_times.append(datetime.datetime.now().timestamp() - self._last_time.timestamp())
            self._avg_time = sum(self._round_times)/len(self._round_times)
        self._last_time = datetime.datetime.now()

        # Check if the last received offer if the opponent is good enough
        if self._isGood(self._last_received_bid):
            # if so, accept the offer
            action = Accept(self._me, self._last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            bid = self._findBid()
            action = Offer(self._me, bid)

        # send the action
        return action

    # This method checks if we would agree with an offer
    def _isGood(self, bid: Bid) -> bool:
        # If there is no bid the agent rejects
        if bid is None:
            return False
        profile = self._profile.getProfile()
        # Checks the average round time
        if self._avg_time is not None:
            # If we are coming close to time deadline the agent drastically go low by changing the beta
            # in the time dependent formula to 2
            if self._progress.getTerminationTime().timestamp() - 10 * self._avg_time <= \
                    datetime.datetime.now().timestamp():
                self._beta = 2
                # Recalculates the minimum utility the agent accepts
                self._accept = \
                    self.get_time_dependent_utility(self._progress.get(time.time() * 1000), 1, self._beta, 1, self._reservation)
        return profile.getUtility(bid) > self._accept

    def _findBid(self) -> Bid:
        progress = self._progress.get(1)
        bids_with_utility = BidsWithUtility.create(self._profile.getProfile(), 5)
        # Calculate the maximum utility (self._accept is the minimum utility we accept calculated by
        # time dependent formula)
        max_bid = self._accept + self._range
        # Select the bids between min and max utility
        all_bids = bids_with_utility.getBids(Interval(Decimal(self._accept), Decimal(max_bid)))
        # If there is less than 10 bids in this range we decrease the minimum utility
        while all_bids.size() < 10:
            self._accept -= self._range
            all_bids = bids_with_utility.getBids(Interval(Decimal(self._accept), Decimal(max_bid)))
            if self._accept <= 0:
                break

        if all_bids.size() == 0:
            return self._most_similar

        # Set the best bid to a random bid or global most similar
        if self._most_similar is None:
            best_bid = all_bids.get(randint(0, all_bids.size() - 1))
        else:
            best_bid = self._most_similar
        # We create a random integer for using as probability
        probability = random.randint(0, 100)

        # Return random 10 percent chance
        if probability >= 90:
            return all_bids.get(randint(0, all_bids.size() - 1))

        # This loop calculates the new points for our global most similar bid
        most_similar_sum = 0
        if self._most_similar is not None:
            for k, v in self._most_similar.getIssueValues().items():
                if (k, v) in self.offers_received:
                    # Give points to the bid depending on how many times an issue with a specific
                    # value is offered by the opponent
                    most_similar_sum += self.offers_received[(k, v)]

        # If the progress is very low opponent modeling is not very accurate
        # This is why we have another strategy for low progress
        # This is the strategy used after low progress strategy
        if progress > 0.05:

            max_points = 0
            # Loop over all the bids in the range
            for bid in all_bids:

                points = 0

                # Loop over issues in a bid
                for k, v in bid.getIssueValues().items():
                    if (k, v) in self.offers_received:
                        # Give points to the bid depending on how many times an issue with a specific
                        # value is offered by the opponent
                        points += self.offers_received[(k, v)]

                # Check if any of the bids is more similar than our old most similar bid
                if points > most_similar_sum:
                    self._most_similar = bid
                    most_similar_sum = points
                    # return most similar bid 45 percent chance
                    best_bid = self._most_similar

                # Return the best bid in the range 45 percent chance
                if probability >= 45:
                    if points > max_points:
                        best_bid = bid
                        max_points = points

        # If progress is too low, we use random strategy
        else:
            points = 0
            new_bid = all_bids.get(randint(0, all_bids.size() - 1))
            # Calculates the points of new bid
            for k, v in new_bid.getIssueValues().items():
                if (k, v) in self.offers_received:
                    # Give points to the bid depending on how many times an issue with a specific
                    # value is offered by the opponent
                    points += self.offers_received[(k, v)]

            # If it has more points than most similar bid, changes this bid to most similar
            if most_similar_sum <= points:
                self._most_similar = new_bid

        return best_bid

    @staticmethod
    def alpha_time(t, t_max, beta, initial_value=0):
        return initial_value + (1 - initial_value) * ((min(t, t_max) / t_max) ** (1 / beta))

    def get_time_dependent_utility(self, t, t_max, beta, max_utility, min_utility, initial_value=0):
        return min_utility + (1 - self.alpha_time(t, t_max, beta, initial_value)) * (max_utility - min_utility)