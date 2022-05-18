import logging
import time
import numpy as np
from typing import cast

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
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter



class Agent67(DefaultParty):
    """
    Template agent that offers random bids until a bid with sufficient utility is offered.
    """

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._last_received_bid: Bid = None
        self.best_offer_opponent: Bid = None
        self.best_bid: Bid = None
        self.calculated_bid: bool = False
        self.opponent_issues = {}
        self.opp_history_bids = ({})
        self.sorted_bid = []

        self.walk_down_counter = 0
        self.curr_walk_down_bid = None
        self.whether_walk_down = True

        self.average_util = 0
        self.issues = []
        self.bid_history = {}
        self.opp_profile = {}

        # Issues to numeric
        self.issue_to_numeric = {}
        self.idx_issue = 1

        # Values to numeric
        self.value_to_numeric = {}
        self.idx_value = 1

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

    

    """
    AgentBernie : Using frequency analysis model with walk-down strategy and boulware-style concession.
    """

    def getDescription(self) -> str:
        return "AgentBernie : Using frequency analysis model with walk-down strategy and boulware-style concession."

    # execute a turn
    def _myTurn(self):

        # Sort the highest bid in decreasing order
        if len(self.sorted_bid) <= 0:
            self.sort_high_bids()
            bid = self.sorted_bid[0]
            action = Offer(self._me, bid)
            return action

        else:
            # Update the opponent profile with the new bid
            self.update_bid_history(self._last_received_bid)
            self.analyse_opp_profile()

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

    #####################################################################################
    ############################## ACCEPTANCE STRATEGY ##################################
    #####################################################################################

    def _isGood(self, bid: Bid) -> bool:
        """
        Checking whether the opponent's offered bid is good or bad.
        """
        if bid is None:
            return False
        profile = self._profile.getProfile()
        progress = self._progress.get(time.time() * 1000)

        # If 90% of the rounds towards the deadline have passed
        # and no progress made. Then switching to the
        # concession strategy
        if progress > 0.90 and profile.getUtility(bid) > 0.4:
            return True

        # 75% of the rounds towards the deadline have passed
        # Using acceptance strategy here called : AC_NEXT
        return progress > 0.75 \
            and profile.getUtility(bid) > profile.getUtility(self._findBid()) \
            and self.batna(bid)

    #####################################################################################
    ############################## BIDDING STRATEGY #####################################
    #####################################################################################

    def _findBid(self) -> Bid:
        """
        Finds the best offer for us and the opponent to 
        reach desirable agreeement and results.
        """
        profile = self._profile.getProfile()

        # Walk-down strategy, stop until offered utility value
        # is below lambda parameter
        if(self.whether_walk_down):
            walk_down_bid = self.walk_down_strategy()
            util_bid = profile.getUtility(walk_down_bid)

            lambda_value = 0.80
            if util_bid > lambda_value:
                return walk_down_bid
            else:
                self.whether_walk_down = False
                return self.find_best_offer()

        return self.find_best_offer()

    def walk_down_strategy(self):
        """
        Walk-down strategy : Starting from the highest until
        the utility is below lambda parameter.
        """
        walk_down_bid = self.sorted_bid[self.walk_down_counter]
        self.curr_walk_down_bid = walk_down_bid
        self.walk_down_counter += + 1

        return walk_down_bid

    def batna(self, bid):
        """
        Checking whether the bid's utility is 
        bove batna utility value.
        """
        profile = self._profile.getProfile()
        reservation_bid = profile.getReservationBid()

        if reservation_bid is None:
            return True
        else:
            return profile.getUtility(bid) > profile.getUtility(reservation_bid)

    def find_best_offer(self) -> Bid:
        """
        Finding 
        """
        for bid in self.sorted_bid:
            found = True

            for issue, value in bid.getIssueValues().items():
                num_issue = self.issue_to_numeric[issue]
                if self.accept_range(issue, value) \
                        and self.batna(bid) \
                        and self.opp_profile[num_issue][1] != -1:
                    continue
                else:
                    found = False
                    break
            if(found):
                return bid
        curr_walk_down_bid = self.walk_down_strategy()
        return curr_walk_down_bid

    #####################################################################################
    ############################## OPPONENT MODELLING ###################################
    #####################################################################################

    def update_bid_history(self, bid):
        """
        Adding new bid/offer to the history, if issue is not recorded in the
        "issue_to_numeric". Assign a numeric representation of the issue and save it in the
        dict.

        Same for values, if there are missing numerical representation for them. Create one in
        "value_to_numeric" dict.
        """
        bid_dict = bid.getIssueValues().items()
        for issue, value in bid_dict:

            # If issue doesn't exist in the categorical-numerical mapping
            # in dictionary "map_issues_to_numeric_and_initialize" then
            # initialize. Same for values
            if issue not in self.issue_to_numeric:
                self.map_issues_to_numeric_and_initialize(issue)
            if value not in self.value_to_numeric:
                self.map_value_to_numeric(value)

            idx_numeric_issue = self.issue_to_numeric[issue]
            self.bid_history[idx_numeric_issue].append(value)

    def analyse_opp_profile(self):
        """
        Calculate the mode and variance of values per issue to
        know the opponent's profile
        """
        for issue, values in self.bid_history.items():
            if issue not in self.opp_profile:
                self.opp_profile[issue] = ()

            # Mapping from categorival to numerical with values from the issue
            numerical_values = [self.value_to_numeric[value]
                                for value in values]

            if(len(numerical_values) == 1):
                self.opp_profile[issue] = (
                    max(numerical_values, key=numerical_values.count), -1)
            else:
                self.opp_profile[issue] = (
                    max(numerical_values, key=numerical_values.count), np.var(numerical_values, ddof=1))

    def accept_range(self, issue, value):
        """
        Accepts when given that the value of the partucular issue is in the
        calculated acceptable range.
        """
        issue_range = self.calculate_acceptable_range(issue)
        if value not in self.value_to_numeric:
            self.map_value_to_numeric(value)

        low = issue_range[0]
        high = issue_range[1]

        return low < self.value_to_numeric[value] < high

    def calculate_acceptable_range(self, issue):
        """
        Calculate ranges by taking a mode and variance into account.
        """
        numerical_issue = self.issue_to_numeric[issue]
        issue_mode = self.opp_profile[numerical_issue][0]
        issue_var = self.opp_profile[numerical_issue][1]

        # Calculating the ranges
        low = issue_mode - issue_var
        high = issue_mode + issue_var

        return low, high

    #####################################################################################
    ############################## HELPER FUNCTIONS #####################################
    #####################################################################################

    def update_opponent_issues(self):
        """
        Keep track of frequencies of the values in bids received by
        the opponents over period of time.
        """

        recentIssues = self._last_received_bid.getIssues()
        recentIssuesValues = self._last_received_bid.getIssueValues()

        for issue in recentIssues:
            if issue in self.opponent_issues:
                if recentIssuesValues[issue] in self.opponent_issues[issue]:
                    self.opponent_issues[issue] = self.opponent_issues[issue][recentIssuesValues[issue]] + 1
                else:
                    self.opponent_issues[issue][recentIssuesValues[issue]] = 1
            else:
                self.opponent_issues[issue][recentIssuesValues[issue]] = 1

    def update_history_opp_issues(self):
        """
        Updates history of opponent's issues
        """
        recentIssuesValues = self._last_received_bid.getIssueValues()
        self.opp_history_bids.append(recentIssuesValues)

    def always_best_bid_init(self) -> Bid:
        """
        Returns the best bid
        """
        if(not self.calculated_bid):
            domain = self._profile.getProfile().getDomain()
            all_bids = AllBidsList(domain)
            profile = self._profile.getProfile()

            best_utility = 0.0

            for x in all_bids:
                curr_utility = profile.getUtility(x)
                if(best_utility < curr_utility):
                    bid = x
                    best_utility = curr_utility

            self.calculated_bid = True
            self.best_bid = bid

            return self.best_bid
        else:
            return self.best_bid

    def sort_high_bids(self):
        """
        Sorting bids based on the utility values
        """
        temp_tuple_bid = []
        if(not self.calculated_bid):
            domain = self._profile.getProfile().getDomain()
            all_bids = AllBidsList(domain)
            profile = self._profile.getProfile()

            for x in all_bids:
                temp_tuple_bid.append((profile.getUtility(x), x))

            temp_tuple_bid = sorted(
                temp_tuple_bid, key=lambda x: x[0], reverse=True)

            self.calculated_bid = True
            self.sorted_bid = [bid[1] for bid in temp_tuple_bid]

    def map_issues_to_numeric_and_initialize(self, issue):
        """
        Map issues which are represented in String to numeric values,
        furthermore it initializes issue-history pair in "bid_history" dict.
        """
        self.issue_to_numeric[issue] = self.idx_issue
        self.bid_history[self.idx_issue] = []
        self.idx_issue = self.idx_issue + 1

    def map_value_to_numeric(self, value):
        """
        Map values which are represented in String to numeric values.
        """
        self.value_to_numeric[value] = self.idx_value
        self.idx_value = self.idx_value + 1

    def calculate_avg_util(self):
        profile = self._profile.getProfile()
        util_avg = 0

        for bid in self.sorted_bid:
            util_avg += profile.getUtility(bid)

        return util_avg / len(self.sorted_bid)
