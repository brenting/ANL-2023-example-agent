import logging
import time
import numpy as np
import copy
from geniusweb.progress.Progress import Progress
from scipy.stats import chisquare
from random import randint
from typing import cast
from time import time as clock
from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Value import Value
from decimal import Decimal
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace import LinearAdditive
from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.profileconnection import ProfileInterface
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList

from .extended_util_space import ExtendedUtilSpace
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter


class Agent22(DefaultParty):

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile: ProfileInterface = None
        self._last_received_bid: Bid = None
        self._progress: Progress = None  # type:ignore
        self._extendedspace: ExtendedUtilSpace = None
        self.issue_names = []
        self.bidList: list[Bid] = []
        self.bidListOpp: list[Bid] = []
        self.weightList: dict[str, Decimal] = {}
        self.weightListOpp: dict[str, Decimal] = {}
        self.issue_value_frequencies = {}
        self.prev_issue_value_frequencies = {}
        self.cc = 1  # concession constant

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

            profile: LinearAdditive = self._profile.getProfile()
            self.weightList = profile.getWeights()
            self.issue_names = list(self.weightList.keys())
            n = len(self.issue_names)
            self.weightListOpp = dict(zip(self.issue_names, np.full(n, Decimal(round(1 / n, 6)))))
            self.issue_value_frequencies = dict(zip(self.issue_names, {}))
        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()
            # if it is an offer, set the last received bid
            if isinstance(action, Offer):
                self._last_received_bid = cast(Offer, action).getBid()
                self.bidListOpp.append(self._last_received_bid)
                self._updateFrequencies(self._last_received_bid)
                self.update_weight_every_window()



        # YourTurn notifies you that it is your turn to act
        elif isinstance(info, YourTurn):
            # execute a turn
            action = self._myTurn()
            if action is Offer:
                self.bidList.append(action.getBid())
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
    # Overrride
    def getDescription(self) -> str:
        return "Agent22"

    # execute a turn
    # Override
    def _myTurn(self):
        self._updateExtUtilSpace()
        # check if the last received offer if the opponent is good enough
        ourBid = self._findBid()
        if self._isGoodNew(self._last_received_bid, ourBid):
            # if so, accept the offer
            action = Accept(self._me, self._last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            bid = ourBid
            action = Offer(self._me, bid)

        # send the action
        return action
        return action

    def _updateExtUtilSpace(self):  # throws IOException
        new_utilspace: LinearAdditive = self._profile.getProfile()
        self._extendedspace = ExtendedUtilSpace(new_utilspace)

    def _findBid(self) -> Bid:
        beta = self._checkStrategyOpp()
        return self.time_dependent_bidding(beta)

    def _getTheirUtility(self, bid: Bid):
        value_estimation = self.val_estimation()
        utility = 0
        for issue in bid.getIssues():
            value = bid.getValue(issue)
            if issue in value_estimation and value in value_estimation[issue]:
                utility += float(self.weightListOpp[issue]) * value_estimation[issue][value]

        return Decimal(utility)

    def _updateFrequencies(self, bid: Bid):
        issue_values = bid.getIssueValues()
        for issue in issue_values.keys():
            value = issue_values[issue]
            if not (issue in self.issue_value_frequencies):
                self.issue_value_frequencies[issue] = {}
            if not (value in self.issue_value_frequencies[issue]):
                self.issue_value_frequencies[issue][value] = 0

            self.issue_value_frequencies[issue][value] += 1

    def _evaluate_bid(self, bid: Bid):
        profile = self._profile.getProfile()
        progress = self._progress.get(time.time() * 1000)

        U_mine = profile.getUtility(bid)
        U_theirs = self._getTheirUtility(bid)
        a = Decimal(1 - progress)

        if a < 1.0 / 2: return U_mine
        if a >= 1.0 / 2: return (a * U_mine + (1 - a) * U_theirs) / 2


    def _checkStrategyOpp(self) -> float:
        opp_bids_length = len(self.bidListOpp)
        if opp_bids_length > 0:
            unique_opp_bids_length = len(set(self.bidListOpp))
            t1 = unique_opp_bids_length / opp_bids_length
            # print(t1)
            if t1 > 0.35:
                return 0.2
            else:
                return 1.8
        else:
            return 0.2

    # Acceptance condition
    def _isGoodNew(self, bid: Bid, plannedBid: Bid) -> bool:
        # the offer is acceptable if it is better than
        # all offers received in the previous time window W
        # or the offer is better than our next planned offer
        # W = [T - (1 - T), T]
        if bid is None:
            return False
        profile = self._profile.getProfile()

        progress = self._progress.get(time.time() * 1000)
        bidsFromW = []
        maxBidFromW = 0
        W = 0.02
        T = 0.98
        if isinstance(profile, UtilitySpace):
            reservation_bid = profile.getReservationBid()
            if reservation_bid is None and progress >= T:
                return True
            reservation_value = 0.3
            if reservation_bid is not None:
                reservation_value = profile.getUtility(reservation_bid)

            receivedBid = self._evaluate_bid(bid)
            # If the opponent's bid is better than our next planned bid, accept
            if (receivedBid > self._evaluate_bid(plannedBid)):
                return True

            # Save bids from window W and save the best one
            if (progress >= T - W and progress < T):
                bidsFromW.append(receivedBid)
                if (receivedBid > maxBidFromW):
                    maxBidFromW = receivedBid

            utility_target = reservation_value * 3 / 2
            # After time T, accept the bid if it is better from the best bid recieved
            # in the previous time window W
            if (progress >= T and receivedBid < utility_target and receivedBid >= maxBidFromW):
                return True

            return receivedBid >= utility_target

    def time_dependent_bidding(self, beta: float) -> Bid:
        progress: float = self._progress.get(time.time() * 1000)
        profile = self._profile.getProfile()

        reservation_bid: Bid = profile.getReservationBid()
        min_util = Decimal(0.6)  # reservation value
        if reservation_bid is not None:
            min_util = Decimal(profile.getUtility(reservation_bid))

        max_util: Decimal = Decimal(1)

        ft1 = Decimal(1)
        if beta != 0:
            ft1 = round(Decimal(1 - pow(progress, 1 / beta)), 6)  # defaults ROUND_HALF_UP
        utilityGoal: Decimal = min_util + (max_util - min_util) * ft1

        options: ImmutableList[Bid] = self._extendedspace.getBids(utilityGoal)
        if options.size() == 0:
            # if we can't find good bid, get max util bid....
            options = self._extendedspace.getBids(self._extendedspace.getMax())

        for bid in options:
            if self._isGoodNew(self._last_received_bid, bid):
                return bid

        # else pick a random one.
        return options.get(randint(0, options.size() - 1))

    def update_weight_every_window(self):
        k = 10
        if len(self.bidListOpp) % k == 0:
            self.weightListOpp = self.oppWeights()
            self.prev_issue_value_frequencies = copy.deepcopy(self.issue_value_frequencies)

    def val_estimation(self) -> dict[str, dict[Value, float]]:
        gamma = 0.5
        freqs = copy.deepcopy(self.issue_value_frequencies)
        value_func = copy.deepcopy(self.issue_value_frequencies)
        for issue in freqs.keys():
            max_value = max(freqs[issue], key=freqs[issue].get)
            for value in freqs[issue].keys():
                value_func[issue][value] = ((1 + freqs[issue][value]) ** gamma) / (
                            (1 + freqs[issue][max_value]) ** gamma)

        return value_func

    def oppWeights(self) -> dict[str, Decimal]:
        alpha = 10  # alpha denotes how much importance is added to weights
        beta = 5  # beta denotes how much this importance matters over time
        e = []  # list of issues that did not change significantly in frequency
        concession = False
        new_weights: dict[str, Decimal] = copy.deepcopy(self.weightListOpp)
        issue_list = self.prev_issue_value_frequencies.keys()
        value_func = self.val_estimation()
        progress = self._progress.get(round(clock() * 1000))
        n = len(issue_list)
        for issue in issue_list:
            # Calculate the frequencies from the currently found values
            frequencies = copy.deepcopy(self.issue_value_frequencies[issue])
            N = sum(frequencies.values())
            for value in frequencies.keys():
                frequencies[value] /= float(N)

            prev_frequencies = copy.deepcopy(self.prev_issue_value_frequencies[issue])
            # Add the newly found values to the previous dictionary
            for value in frequencies.keys():
                if value not in prev_frequencies:
                    prev_frequencies[value] = 0
            # Calculate the frequencies from the previous found values
            N = sum(prev_frequencies.values())
            for value in prev_frequencies.keys():
                prev_frequencies[value] /= float(N)

            # Do a chi squared distribution test on the frequencies to check if they have changed significantly
            obs = list(frequencies.values())
            exp = list(prev_frequencies.values())
            _, p_val = chisquare(f_obs=obs, f_exp=exp)
            # If our frequencies did not change significantely add this issue to e
            if p_val > 0.05:
                e.append(issue)
            else:
                # Calculate the expected value for the utility for each issue value and compare with the previous found one
                prev_expected = {k: prev_frequencies[k] * value_func[issue][k] for k in prev_frequencies}
                expected = {k: frequencies[k] * value_func[issue][k] for k in frequencies}
                if sum(expected.values()) < sum(prev_expected.values()):
                    concession = True

        if len(e) != len(issue_list) and concession:
            for issue in e:
                delta_t = Decimal(alpha * (1 - progress ** beta))
                new_weights[issue] += delta_t

        # Normalize weights
        summed = sum(new_weights.values())
        for key in new_weights:
            new_weights[key] = Decimal(round(new_weights[key] / summed, 6))

        # print(new_weights)
        return new_weights
