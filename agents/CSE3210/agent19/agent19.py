import logging
import time
from random import randint
from typing import cast
import random
import functools

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.ActionWithBid import ActionWithBid
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
from geniusweb.opponentmodel.FrequencyOpponentModel import FrequencyOpponentModel
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter
import numpy as np


class Acceptinator:
    def __init__(self, bid_window, acceptance_threshold, trajectory_threshold):
        self.my_bids_utility = []
        self.my_bid_window_average = []
        self.other_bids_utility = []
        self.other_bid_window_average = []
        self.min_bid = 1
        self.max_bid = 0
        self.bid_window = bid_window
        self.acceptance_threshold = acceptance_threshold
        self.bid_trajectory = ""
        self.trajectory_threshold = trajectory_threshold
        self.currentBid = None

    def process_bid_utility(self, my_utility, other_agent_utility):
        self.my_bids_utility.append(float(my_utility))
        self.other_bids_utility.append(float(other_agent_utility))
        self.min_bid = min(self.min_bid, other_agent_utility)
        self.max_bid = max(self.max_bid, other_agent_utility)

    def get_current_window_average(self):
        """get the current window average of two agents based on the data stored by the process_bid utility"""
        if len(self.my_bids_utility) - self.bid_window > 1:
            my_window_utility_bid_mean = np.mean(self.my_bids_utility[len(self.my_bids_utility) - self.bid_window:])
            other_window_utility_bid_mean = np.mean(
                self.other_bids_utility[len(self.my_bids_utility) - self.bid_window:])
            self.my_bid_window_average.append(my_window_utility_bid_mean)
            self.other_bid_window_average.append(other_window_utility_bid_mean)

            return (my_window_utility_bid_mean, other_window_utility_bid_mean)
        return None

    def get_current_window_average_trend(self):
        """get the current window average trend of two agents based on the data stored by the process_bid utility"""
        if len(self.my_bids_utility) - self.bid_window > 1:
            curr_window_bid = np.mean(self.my_bids_utility[len(self.my_bids_utility) - self.bid_window:])
            curr_window_utility = np.mean(self.other_bids_utility[len(self.my_bids_utility) - self.bid_window:])
            self.my_bid_window_average.append(curr_window_bid)
            self.other_bid_window_average.append(curr_window_utility)
            # try to establish what is the trajectory of the other agent
            if len(self.my_bid_window_average) >= 1:
                if self.my_bid_window_average[len(self.my_bid_window_average) - 2] < self.my_bid_window_average[
                    len(self.my_bid_window_average) - 1]:
                    if self.my_bid_window_average[
                        len(self.my_bid_window_average) - 1] + self.trajectory_threshold >= \
                            self.my_bid_window_average[len(self.my_bid_window_average) - 1]:
                        pass
                    else:
                        self.bid_trajectory = "DOWNTREND"
                else:
                    # check if the bid utility given by the other agent represents an uptrend
                    if self.my_bid_window_average[
                        len(self.my_bid_window_average) - 1] - self.trajectory_threshold >= \
                            self.my_bid_window_average[len(self.my_bid_window_average) - 1]:
                        pass
                    else:
                        self.bid_trajectory = "UPTREND"

            return (curr_window_bid, curr_window_utility)
        return None

    def is_bid_good_enough_utility(self, utility, progress):
        if progress < 0.6:
            return False

        return utility <= self.other_bid_window_average[len(self.other_bid_window_average) - 1]

    def is_bid_good_enough(self, my_utility, other_utility, progress):
        """check if received bid is good enough with respect to our agent's
                average utility over a time window and time (progress)"""
        if progress > 0.35 and other_utility >= my_utility:
            return True
        elif progress < 0.25:
            return False
        elif len(self.my_bid_window_average) >= 1 and progress < 0.7 and other_utility >= self.my_bid_window_average[
            len(self.my_bid_window_average) - 1]:
            return True

    def is_bid_good_enough_trend(self, progress):
        """check if the bid is good enough with respect to time, the other agent utility, and
                our average utility at the end of each time window"""
        if self.bid_trajectory == "DOWNTREND" and progress < 0.6:
            return False

        return self.get_current_window_average()[1] / self.get_current_window_average()[0] > self.acceptance_threshold


class Agent19(DefaultParty):
    """
    Group19_NegotiationAssignment_Agent first sorts the bids according to their utility
    and offer random bids with a high utily for him in the begining and do frequency oponent modeling
    after 20% of the rounds he only offers bids that have a good utility for him and its oponent
    """

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._last_received_bid: Bid = None
        self._sortedList = None
        self._opponent = None
        self._opponentAction = None
        self.counter = 0

        self.acceptinator = Acceptinator(20, 1.7, 0.05)

        self.bestBid = None
        self.bestBidsFirst = None
        self.bestBidsSecond = None
        self.bestBidsThird = None
        self.bestBidsFourth = None
        self.bestBidsFifth = None

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
            opponent = FrequencyOpponentModel.create()
            opponent = opponent.With(self._profile.getProfile().getDomain(), None)
            self._opponent = opponent
        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()

            # if it is an offer, set the last received bid
            if isinstance(action, Offer):
                self._opponentAction = action
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
        return "Agent19"

    # execute a turn
    def _myTurn(self):
        # check if the last received offer if the opponent is good enough
        self._opponent = self._opponent.WithAction(self._opponentAction, self._progress)
        if self._isGood(self._last_received_bid):
            # if so, accept the offer
            action = Accept(self._me, self._last_received_bid)

        else:
            # if not, find a bid to propose as counter offer
            bid = self._findBid()

            b = self._opponent.getUtility(self._last_received_bid)
            self.acceptinator.currentBid = bid

            # process the bid in the acceptinator
            self.acceptinator.process_bid_utility(self._profile.getProfile().getUtility(bid), b)




            action = Offer(self._me, bid)

        # send the action
        return action

        # method that checks if we would agree with an offer
        # method that checks if we would agree with an offer

    def _isGood(self, bid: Bid) -> bool:
        if bid is None:
            return False

        profile = self._profile.getProfile()

        progress = self._progress.get(1)

        if self.bestBid is None or profile.getUtility(bid) > profile.getUtility(self.bestBid):
            self.bestBid = bid

        ##Update acceptinator
        if self.acceptinator.currentBid is not None and self.acceptinator.is_bid_good_enough(profile.getUtility(self.acceptinator.currentBid),
                                                profile.getUtility(bid), progress):
            return True

        # very basic approach that accepts if the offer is valued above 0.6 and
        # 80% of the rounds towards the deadline have passed
        return profile.getUtility(bid) > 0.6 + 0.4 * (1 - progress)

    def _findBid(self) -> Bid:
        # compose a list of all possible bids

        domain = self._profile.getProfile().getDomain()
        profile = self._profile.getProfile()
        progress = self._progress.get(1)

        if (self._sortedList == None):
            """Sort the list. Highest utility first"""
            all_bids = AllBidsList(domain)
            self._sortedList = sorted(all_bids, key=functools.cmp_to_key(
                lambda bid1, bid2: profile.getUtility(bid2) - profile.getUtility(bid1)))

        if (progress <= 0.2):
            bestBids = [x for x in self._sortedList if (profile.getUtility(x) >= float(
                profile.getUtility(self._sortedList[0])) * 0.95 and profile.getUtility(x) <= profile.getUtility(
                self._sortedList[0]))]
            bid = random.choice(bestBids)

        elif (progress > 0.2 and progress <= 0.3):

            bestBids = [x for x in self._sortedList if (profile.getUtility(x) >= float(
                profile.getUtility(self._sortedList[0])) * 0.9 and profile.getUtility(x) <= profile.getUtility(
                self._sortedList[0]))]
            bid = random.choice(bestBids)

        elif (progress > 0.3 and progress <= 0.4):
            bestBids = [x for x in self._sortedList if (profile.getUtility(x) >= float(
                profile.getUtility(self._sortedList[0])) * 0.85 and profile.getUtility(x) <= profile.getUtility(
                self._sortedList[0]))]
            bid = random.choice(bestBids)

        elif (progress > 0.4 and progress <= 0.65):
            if (self.bestBidsFirst == None):
                bestBids = [x for x in self._sortedList if (profile.getUtility(x) >= float(
                    profile.getUtility(self._sortedList[0])) * 0.8 and profile.getUtility(x) < 0.95)]
                self.bestBidsFirst = [x for x in bestBids if
                                      (self._opponent.getUtility(x) >= 0.35 and self._opponent.getUtility(x) < 0.95)]
                self.bestBidsFirst = sorted(self.bestBidsFirst, key=functools.cmp_to_key(
                    lambda bid1, bid2: self._opponent.getUtility(bid2) - self._opponent.getUtility(bid1)))
                util = 0.35
                while (len(self.bestBidsFirst) < 2):
                    self.bestBidsFirst = [x for x in bestBids if (
                                self._opponent.getUtility(x) >= util and self._opponent.getUtility(x) < 0.95)]
                    self.bestBidsFirst = sorted(self.bestBidsFirst, key=functools.cmp_to_key(
                        lambda bid1, bid2: self._opponent.getUtility(bid2) - self._opponent.getUtility(bid1)))
                    util = util - 0.01
            length = len(self.bestBidsFirst)
            counter = random.randint(0, length - 1)
            bid = self.bestBidsFirst[counter]

        elif (progress > 0.65 and progress <= 0.8):
            """Sort the list. Highest utility first and also consider opponents utility"""
            if (self.bestBidsSecond == None):
                bestBids = [x for x in self._sortedList if (profile.getUtility(x) >= float(
                    profile.getUtility(self._sortedList[0])) * 0.75 and profile.getUtility(x) < 0.95)]
                self.bestBidsSecond = [x for x in bestBids if
                                       (self._opponent.getUtility(x) >= 0.4 and self._opponent.getUtility(x) < 0.95)]
                self.bestBidsSecond = sorted(self.bestBidsSecond, key=functools.cmp_to_key(
                    lambda bid1, bid2: self._opponent.getUtility(bid2) - self._opponent.getUtility(bid1)))
                util = 0.45
                while (len(self.bestBidsSecond) < 2):
                    """ Check if there are bids in bidspace according to our util and opponents. If there is not lower the util of the opponent """
                    self.bestBidsSecond = [x for x in bestBids if (
                                self._opponent.getUtility(x) >= util and self._opponent.getUtility(x) < 0.95)]
                    self.bestBidsSecond = sorted(self.bestBidsSecond, key=functools.cmp_to_key(
                        lambda bid1, bid2: self._opponent.getUtility(bid2) - self._opponent.getUtility(bid1)))
                    util = util - 0.025

            length = len(self.bestBidsSecond)
            counter = random.randint(0, length - 1)
            bid = self.bestBidsSecond[counter]
        elif (progress > 0.8 and progress <= 0.95):
            if (self.bestBidsThird == None):
                bestBids = [x for x in self._sortedList if
                            (profile.getUtility(x) >= 0.65 and profile.getUtility(x) < 0.95)]
                self.bestBidsThird = [x for x in bestBids if
                                      (self._opponent.getUtility(x) >= 0.4 and self._opponent.getUtility(x) < 0.95)]
                self.bestBidsThird = sorted(self.bestBidsThird, key=functools.cmp_to_key(
                    lambda bid1, bid2: self._opponent.getUtility(bid2) - self._opponent.getUtility(bid1)))
                util = 0.5
                while (len(self.bestBidsThird) < 2):
                    """ Check if there are bids in bidspace according to our util and opponents. If there is not lower the util of the opponent """
                    self.bestBidsThird = [x for x in bestBids if (
                                self._opponent.getUtility(x) >= util and self._opponent.getUtility(x) < 0.95)]
                    self.bestBidsThird = sorted(self.bestBidsThird, key=functools.cmp_to_key(
                        lambda bid1, bid2: self._opponent.getUtility(bid2) - self._opponent.getUtility(bid1)))
                    util = util - 0.025

            length = len(self.bestBidsThird)
            counter = random.randint(0, length - 1)
            bid = self.bestBidsThird[counter]
        elif (progress > 0.95 and progress <= 0.99):
            if (self.bestBidsFourth == None):
                bestBids = [x for x in self._sortedList if
                            (profile.getUtility(x) >= 0.60 and profile.getUtility(x) < 0.95)]
                self.bestBidsFourth = [x for x in bestBids if
                                       (self._opponent.getUtility(x) >= 0.5 and self._opponent.getUtility(x) < 0.95)]
                self.bestBidsFourth = sorted(self.bestBidsFourth, key=functools.cmp_to_key(
                    lambda bid1, bid2: self._opponent.getUtility(bid2) - self._opponent.getUtility(bid1)))
                util = 0.5
                while (len(self.bestBidsFourth) < 2):
                    """ Check if there are bids in bidspace according to our util and opponents. If there is not lower the util of the opponent """
                    self.bestBidsFourth = [x for x in bestBids if (
                                self._opponent.getUtility(x) >= util and self._opponent.getUtility(x) < 0.95)]
                    self.bestBidsFourth = sorted(self.bestBidsFourth, key=functools.cmp_to_key(
                        lambda bid1, bid2: self._opponent.getUtility(bid2) - self._opponent.getUtility(bid1)))
                    util = util - 0.025

            length = len(self.bestBidsFourth)
            counter = random.randint(0, length - 1)
            bid = self.bestBidsFourth[counter]

        else:
            if (self.bestBidsFifth == None):
                bestBids = [x for x in self._sortedList if
                            (profile.getUtility(x) >= 0.55 and profile.getUtility(x) < 0.95)]
                self.bestBidsFifth = [x for x in bestBids if
                                      (self._opponent.getUtility(x) >= 0.5 and self._opponent.getUtility(x) < 0.95)]
                self.bestBidsFifth = sorted(self.bestBidsFifth, key=functools.cmp_to_key(
                    lambda bid1, bid2: self._opponent.getUtility(bid2) - self._opponent.getUtility(bid1)))
                util = 0.55
                while (len(self.bestBidsFifth) < 2):
                    """ Check if there are bids in bidspace according to our util and opponents. If there is not lower the util of the opponent """
                    self.bestBidsFifth = [x for x in bestBids if (
                                self._opponent.getUtility(x) >= util and self._opponent.getUtility(x) < 0.95)]
                    self.bestBidsFifth = sorted(self.bestBidsFifth, key=functools.cmp_to_key(
                        lambda bid1, bid2: self._opponent.getUtility(bid2) - self._opponent.getUtility(bid1)))
                    util = util - 0.025
            length = len(self.bestBidsFifth)
            counter = random.randint(0, length - 1)
            bid = self.bestBidsFifth[counter]
        return bid
