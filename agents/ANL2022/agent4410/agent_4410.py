import logging
import time
from datetime import datetime
from decimal import Decimal
from random import randrange
from typing import cast

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
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter

NUM_OF_MOVES_FOR_EXPLORE = 800


class Agent4410(DefaultParty):
    _bid_to_utility = {}
    _sorted_bids = []
    _top_10_present_utility = -1
    _top_5_present_utility = -1
    _explore_state = True
    _received_issues_count = {}
    _num_of_counter_bids = 0
    _last_received_bid: Bid = None
    _my_weights = None
    _opponent_weights = None
    _precent_of_bids = 0.02

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)

    def notifyChange(self, info: Inform):
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

            start = time.time()
            self._generate_run_data()
            end = time.time()
            self.getReporter().log(logging.WARNING, f"Init took: {end - start} secs")
            self.getReporter().log(logging.WARNING, "")
        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()
            # if it is an offer, set the last received bid
            if isinstance(action, Offer):
                self._last_received_bid = cast(Offer, action).getBid()
        # YourTurn notifies you that it is your turn to act
        elif isinstance(info, YourTurn):
            # execute a turn
            action = self._myTurn()

            if isinstance(self._progress, ProgressRounds):
                self._progress = self._progress.advance()

            self.getConnection().send(action)
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
        return "Agent 4410"

    def _update_precent_of_bids(self):
        curr = datetime.now()
        terminationTime = self._progress.getTerminationTime()
        diff = terminationTime - curr
        diff_in_milli_secs = diff.total_seconds() * 1000

        remaining_time_share = diff_in_milli_secs / self._progress._duration

        if remaining_time_share <= 1 / 12:
            self._precent_of_bids = 0.05
        elif remaining_time_share <= 1 / 3:
            self._precent_of_bids = 0.08
        elif remaining_time_share <= 1 / 2:
            self._precent_of_bids = 0.05
        elif remaining_time_share <= 2 / 3:
            self._precent_of_bids = 0.03
        else:
            self._precent_of_bids = 0.01

    def _myTurn(self):
        profile = self._profile.getProfile()

        self._update_precent_of_bids()

        bid_size = len(self._sorted_bids)
        top_5_present_index = round(bid_size * self._precent_of_bids)

        top_5_present_utility = self._bid_to_utility[self._sorted_bids[top_5_present_index]]

        if self._last_received_bid:
            last_offer_utility = profile.getUtility(self._last_received_bid)
            if last_offer_utility >= top_5_present_utility:
                # This is our top 5% - accepting it!
                self.getReporter().log(logging.INFO, f"Accepting offer with utility: {last_offer_utility}")

                return Accept(self._me, self._last_received_bid)

        if self._explore_state:
            return self._explore()
        else:
            return self._exploitation()

    def _explore(self):
        if self._last_received_bid:
            self._update_response_tracking()

        # Pick a random bid from the 10% and offer it
        bid_index = randrange(round(len(self._sorted_bids) * self._precent_of_bids))
        next_bid = self._sorted_bids[bid_index]

        # Update state
        self._explore_state = self._num_of_counter_bids <= NUM_OF_MOVES_FOR_EXPLORE

        if not self._explore_state:
            self.getReporter().log(logging.INFO, "Changing state to exploit!")

        return Offer(self._me, next_bid)

    def _update_response_tracking(self):
        last_bid_issue_values = self._last_received_bid.getIssueValues()

        # Track number of values per issues
        for issue in last_bid_issue_values:
            value = last_bid_issue_values[issue]
            if self._received_issues_count.get(issue) is None:
                self._received_issues_count[issue] = {}

            if self._received_issues_count[issue].get(value) is None:
                self._received_issues_count[issue][value] = 0

            self._received_issues_count[issue][value] += 1
        self._num_of_counter_bids += 1

    def _exploitation(self):
        # Keep updating our data
        if self._last_received_bid:
            self._update_response_tracking()

        return self._recalculate_our_weights()

    def _recalculate_our_weights(self, ):
        for bid in self._sorted_bids_to_utility.keys():
            for issue in bid.getIssues():
                if bid.getValue(issue) in self._received_issues_count[issue].keys():
                    weight = Decimal(
                        self._received_issues_count[issue][bid.getValue(issue)] / self._num_of_counter_bids)
                    if self._received_issues_count[issue][bid.getValue(issue)] < self._num_of_counter_bids / 2:
                        self._sorted_bids_to_utility[bid] += Decimal(0.02) * weight
                    else:
                        self._sorted_bids_to_utility[bid] += Decimal(0.005) * weight
                else:
                    self._sorted_bids_to_utility[bid] -= Decimal(0.001)

        self._sorted_bids = sorted(self._sorted_bids_to_utility, key=lambda bid: self._sorted_bids_to_utility[bid],
                                   reverse=True)
        # TODO: Smart randomaization by time left (maybe add sleep if we have lots of time (to scare timebase opponents))
        return Offer(self._me, self._sorted_bids[randrange(round(len(self._sorted_bids) * self._precent_of_bids))])

    def _load_opponent_weights(self):
        self._opponent_weights = {}

        # Calculation of the weights
        for issue in self._received_issues_count:
            self._opponent_weights[issue] = {}
            issue_values = self._received_issues_count[issue]

            for value in issue_values:
                self._opponent_weights[issue][value] = issue_values[value] / self._num_of_counter_bids

    def _load_my_weights(self):
        self._my_weights = {}

        # Change to The TOP NUM_OF_MOVES_FOR_EXPLORE
        num_of_items = round(len(self._sorted_bids) / 10)

        # Summing the top 10% items
        for i in range(num_of_items):
            bid = self._sorted_bids[i].getIssueValues()

            # Takes all our bids and sums up the ocurrences of each issue
            for issue in bid:
                value = bid[issue]
                if self._my_weights.get(issue) is None:
                    self._my_weights[issue] = {}

                if self._my_weights[issue].get(value) is None:
                    self._my_weights[issue][value] = 0

                self._my_weights[issue][value] += 1

        # Calculation of the weights
        for issue in self._my_weights:
            issue_values = self._my_weights[issue]

            for value in issue_values:
                self._my_weights[issue][value] /= num_of_items

    def _generate_run_data(self):
        profile = self._profile.getProfile()
        domain = self._profile.getProfile().getDomain()

        all_bids = AllBidsList(domain)
        self._bid_to_utility = {bid: profile.getUtility(bid) for bid in all_bids}

        # For Future uses
        self._sorted_bids_to_utility = {k: v for k, v in
                                        sorted(self._bid_to_utility.items(), key=lambda item: item[1], reverse=True)}

        self._sorted_bids = sorted(self._bid_to_utility, key=lambda bid: self._bid_to_utility[bid], reverse=True)

        bid_size = len(self._sorted_bids)
        top_10_present_index = round(bid_size / 100 * 10)
        top_5_present_index = round(bid_size / 100 * 5)

        self._top_10_present_utility = self._bid_to_utility[self._sorted_bids[top_10_present_index]]
        self._top_5_present_utility = self._bid_to_utility[self._sorted_bids[top_5_present_index]]
