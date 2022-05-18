import logging
import time
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
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter


class Agent27(DefaultParty):
    """
    Agent that offers bids based on opponent modelling until an agreement is reached.
    """

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._last_received_bid: Bid = None
        self.latest_bid: Bid = None
        self.all_bids = []
        self.opponent_preferences = []
        self.opponent_value_count = {}
        self.all_good_bids = []
        self.all_previously_offered_bids = []
        self.not_important_issues = []
        self.middle_issues = []
        self.all_available_bids_sorted = []

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
        return "Group 27 agent for Collaborative AI course"

    # Initial setup
    def init(self):
        profile = self._profile.getProfile()
        """ Determine which the not important issues are and save them """
        self.get_not_important_issues()

        """
            Initialize dictionary where we store the count of each value for each issue in opponent's bids
            Used for opponent modelling
        """
        issues = profile.getDomain().getIssues()
        for issue in issues:
            self.opponent_value_count[issue] = {}
            for value in profile.getDomain().getValues(issue):
                self.opponent_value_count[issue][value] = 0
        """ Save a list of all bids in the domain ordered by utility """
        self.order_bids()

    """
        Every time we receive a bid, add 1 to the counter for that value
        Used for opponent modelling
    """

    def update_opponent_counts(self):
        lrb = self._last_received_bid
        for issue in lrb.getIssues():
            self.opponent_value_count[issue][lrb.getValue(issue)] += 1

    # execute a turn
    def _myTurn(self):
        profile = self._profile.getProfile()

        # Initial setup
        if not self.opponent_value_count:
            self.init()

        if self._last_received_bid is not None:
            """ We update the count for each value for each issue of our opponent """
            self.update_opponent_counts()
            """ We update the list of all issues sent by our opponent """
            self.all_bids.append((self._last_received_bid, profile.getUtility(self._last_received_bid)))

        if self._isGood(self._last_received_bid):
            """ if so, accept the offer """
            action = Accept(self._me, self._last_received_bid)
        else:
            """ if not, find a bid to propose as counter offer """
            bid = self._findBid()
            action = Offer(self._me, bid)
            self.latest_bid = bid

        """ send the action """
        return action

    """
        Method that decides whether an offer is good or not

        Parameters
        ----------
        bid: the offer that is received/ to be send
    """

    def _isGood(self, bid: Bid) -> bool:
        if bid is None:
            return False

        progress = self._progress.get(time.time() * 1000)
        profile = self._profile.getProfile()

        if progress < 0.85:
            if float(profile.getUtility(bid)) > 1 - progress / 4.5:
                return True
        elif progress < 0.95:
            if float(profile.getUtility(bid)) > 1 - progress / 2.8:
                return True
        elif progress < 0.99:
            if float(profile.getUtility(bid)) > 1 - progress / 1.8:
                return True
        else:
            return True

        return False

    def _findBid(self) -> Bid:

        bid_offer = self.get_suitable_bid()[0][0]
        if bid_offer is not None:
            self.all_previously_offered_bids.append(bid_offer)
        if bid_offer is None:
            """ When we have not offered a bid, offer highest preference """
            if len(self.all_previously_offered_bids) == 0:
                bid = self.get_highest_bid()
            else:
                """  since no new good offers are available, start offering what we have already offered before
                (starting from the best available offers) """
                bid = self.all_previously_offered_bids.pop(0)
                self.all_previously_offered_bids.append(bid)
        else:
            bid = bid_offer
        # print("Bid utility------------", self._profile.getProfile().getUtility(bid))

        return bid

    """
        Selects a favorable bid for the opponent based on issues that are not important to us,
        but we consider them to be important fo the opponent.
    """

    def get_suitable_bid(self):
        all_bids = self.all_available_bids_sorted

        opponent_desired_bid = self.get_opponent_info_good()
        not_important_issues = self.not_important_issues

        chosen_bid = None
        chosen_bid_utility = None

        for bid, bid_utility in all_bids:
            counter = 0
            if bid not in self.all_previously_offered_bids:
                if opponent_desired_bid is not None:
                    for not_important_issue in not_important_issues:
                        if bid.getIssueValues().get(not_important_issue) == opponent_desired_bid.get(
                                not_important_issue):
                            counter += 1

                if (opponent_desired_bid is not None or counter == len(not_important_issues)) and self._isGood(bid):
                    chosen_bid = bid
                    chosen_bid_utility = bid_utility
                    break

        return [(chosen_bid, chosen_bid_utility)]

    """
        Sorts all available bids on utility.
    """
    def order_bids(self):
        domain = self._profile.getProfile().getDomain()
        all_bids = AllBidsList(domain)

        bids_with_utility = []

        for bid in all_bids:
            bids_with_utility.append((bid, self._profile.getProfile().getUtility(bid)))

        bids_with_utility = sorted(bids_with_utility, key=lambda item: -item[1])
        self.all_available_bids_sorted = bids_with_utility

    """
        Sorts all bids and selects the one with highest utility.
    """
    def get_highest_bid(self):
        domain = self._profile.getProfile().getDomain()
        all_bids = AllBidsList(domain)

        bids_with_utility = []

        for bid in all_bids:
            bids_with_utility.append((bid, self._profile.getProfile().getUtility(bid)))

        bids_with_utility = sorted(bids_with_utility, key=lambda item: -item[1])
        return bids_with_utility[0][0]

    """
        Returns a dictionary where the keys are the issues
        and the values are the most often occurring value for this issue
    """
    def get_opponent_info_good(self):
        """ If we have too few of our opponent's bids, return nothing """
        if len(self.all_bids) < 2:
            return None

        issues = self._profile.getProfile().getDomain().getIssues()

        opponent_counts = self.opponent_value_count
        demanded_best_offer = {}

        """ For each issue, sort by the number of occurrences of each value and take the highest """
        for issue in issues:
            opponent_values = opponent_counts[issue]
            sorted_dict = dict(sorted(opponent_values.items(), key=lambda item: item[1]))
            opponent_val = list(sorted_dict.keys())[-1]
            demanded_best_offer[issue] = opponent_val

        return demanded_best_offer

    """
        Returns two arrays containing issues that are not important and issues that are somewhat
        important respectively.
    """

    def get_not_important_issues(self):
        domain = self._profile.getProfile().getDomain()
        issues = domain.getIssues()
        weights = []
        not_important_issues = []
        middle_issues = []

        for issue in issues:
            """ Weight by issue """
            weights.append(self._profile.getProfile().getWeight(issue))

        for issue in issues:
            w = self._profile.getProfile().getWeight(issue)
            if w < 0.15 * float(max(weights)):
                not_important_issues.append(issue)
            elif w < 0.5 * float(max(weights)):
                middle_issues.append(issue)
        self.not_important_issues = not_important_issues
        self.middle_issues = middle_issues
        return not_important_issues, middle_issues
