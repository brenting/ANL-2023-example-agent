import decimal
import logging
import time
import operator
from random import randint
from typing import cast, Set
from bisect import bisect_left

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
from geniusweb.profile.FullOrdering import FullOrdering
from geniusweb.profile.PartialOrdering import PartialOrdering
from geniusweb.profile.utilityspace.DiscreteValueSetUtilities import DiscreteValueSetUtilities
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from geniusweb.profile.utilityspace.LinearAdditiveUtilitySpace import LinearAdditiveUtilitySpace
from geniusweb.profile.utilityspace.NumberValueSetUtilities import NumberValueSetUtilities
from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.profile.utilityspace.ValueSetUtilities import ValueSetUtilities
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressRounds import ProgressRounds
from geniusweb.references.ProfileRef import ProfileRef
from tudelft_utilities_logging.Reporter import Reporter


class Agent7(DefaultParty):
    """
    Template agent that offers random bids until a bid with sufficient utility is offered.
    """

    listOfUtil = [];
    utilBidMap = dict();

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile: ProfileRef = None
        self._last_received_bid: Bid = None
        self._last_offer: Bid = None

        self._all_offers: list = []
        self._progress_offset = 0

        self._is_trading = False
        self._trade_offers = []
        self._trade_offer_index = 0

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
            ####Very important line to set up the list of possible values####
            ####Takes a lot of time####
            self._createLists()

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
        return "Agent7"

    # execute a turn
    def _myTurn(self):

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

    # method that checks if we would agree with an offer
    def _isGood(self, bid: Bid) -> bool:
        if bid is None:
            return False
        profile = self._profile.getProfile()

        progress = self._progress.get(time.time() * 1000)

        accpet_value = [0.9, 0.8, 0.7, 0.9, 0.5]
        next_step = [0, 0.2, 0.4, 0.9, 0.95, 1]
        optimal_util =0
        for i, x in enumerate(next_step):
            if progress <= x and x != 0:
                optimal_util = accpet_value[i-1]
                break




        # # very basic approach that accepts if the offer is valued above 0.6 and
        # # 80% of the rounds towards the deadline have passed
        # return profile.getUtility(bid) > 0.6 and progress > 0.8

        return profile.getUtility(bid) >= optimal_util #profile.getUtility(lowest_acceptable)

    def _findBid(self) -> Bid:
        # Decide whether we are trading off or continuing with our strategy

        # If no last offer and not trading, go on with the strategy
        bid = None
        self._progress_offset = 0

        while bid is None or bid in self._all_offers and self._progress_offset < 0.05:
            if self._last_offer == None or self._is_trading == False:
                bid = self._findStategyBid()
            else:
                bid = self._findTradeOff()

            self._progress_offset += 0.001
            #print(bid)


        self._all_offers.append(bid)
        if bid == None:
            print("Returning bid: " + str(bid))

        return bid

    # Duyemo's strategy
    def _findStategyBid(self):
        self._issue_index = 0
        self._value_index = 0

        upper_lower = [[1, 0.9], [1, 0.8], [1, 0.7], [1, 0.6], [0.9, 0.5], [0.8, 0.5], [1, 0.8], [1, 0.5]]
        next_step = [0, 0.05, 0.15, 0.3, 0.5, 0.7, 0.85, 0.95, 1]
        #upper_lower = [[1,0.8],[1,0.6],[1,0.7]]
        #next_step = [0, 0.5,1]

        progress = self._progress.get(time.time() * 1000)

        for i, x in enumerate(next_step):
            if progress <= x and x != 0:
                step_size = x - next_step[i - 1]
                step_progress = progress - next_step[i - 1]
                upper_lower_factor = step_progress / step_size
                optimal_util = (1 - upper_lower_factor) * upper_lower[i - 1][0] + (upper_lower_factor) * \
                               upper_lower[i - 1][1] + self._progress_offset

                # print("####################")
                # print(step_size)
                # print(step_progress)
                # print(upper_lower_factor)
                # print(optimal_util)
                # print("####################")
                closest = self._take_closest(self.listOfUtil, decimal.Decimal(optimal_util))
                bid = self.utilBidMap[closest]

                self._last_offer = bid
                self._is_trading = True
                self._trade_offers = []

                return bid

    def _createIssueMap(self):
        lau: LinearAdditive = cast(LinearAdditive, self._profile.getProfile())

        issues = self._profile.getProfile().getDomain().getIssues();

        for issue in issues:
            self._issue_by_weight[issue] = lau.getWeight(issue)

        self._issue_by_weight = sorted(self._issue_by_weight.items(), key=operator.itemgetter(1))

        print(self._issue_by_weight)

    def _findTradeOff(self):
        if len(self._trade_offers) == 0:
            self._trade_offer_index = 0
            # Find all trade offers possible with same utility
            current_bid = self._last_offer.getIssueValues()

            lau: LinearAdditive = cast(LinearAdditive, self._profile.getProfile())

            issues = self._profile.getProfile().getDomain().getIssues();
            utils = lau.getUtilities()

            for issue in issues:
                weight = lau.getWeight(issue)
                values = self._profile.getProfile().getDomain().getIssuesValues()[issue]
                valueSet: ValueSetUtilities = utils.get(issue)

                for value in values:
                    newUtil = valueSet.getUtility(value)
                    if current_bid.get(issue) != value and \
                            abs(newUtil - valueSet.getUtility(current_bid.get(issue))) * weight < 0.05:
                        # New bid has almost same util
                        newBid = self._last_offer.getIssueValues()

                        newBid[issue] = value

                        self._trade_offers.append(Bid(newBid))
        if self._trade_offer_index < len(self._trade_offers):
            bid = self._trade_offers[self._trade_offer_index];

            self._trade_offer_index += 1
            return bid

        self._is_trading = False
        return self._findStategyBid()
        """
        # Get all weight to calculate util change



        # Find a bid with same util, but different offers.

        current_bid = self._last_offer.getIssueValues()

        issues: Set[str] = self._last_offer.getIssues()
        values: Set[str] = self._profile.getProfile().getDomain().getIssuesValues()

        # Check if cast is valid, should always be
        # if isinstance(self._profile.getProfile(), LinearAdditiveUtilitySpace):
        #    print("Tewst")

        lau: LinearAdditive = cast(LinearAdditive, self._profile.getProfile())

        current_issue = self._issue_by_weight[self._issue_index]

        utils = lau.getUtilities()
        # Get value set of the lowest weight issue
        valueSet: ValueSetUtilities = utils.get(current_issue[0])

        values = self._profile.getProfile().getDomain().getIssuesValues()[current_issue[0]]
        sorted_values = {}

        for value in values:
            sorted_values[value] = valueSet.getUtility(value)

        sorted_values = sorted(sorted_values.items(), key=operator.itemgetter(1), reverse=True)

        current_bid[current_issue[0]] = list(sorted_values)[self._value_index][0];

        self._value_index += 1

        if self._value_index >= len(sorted_values):
            self._value_index = 0
            self._issue_index += 1

        print(current_bid)

        return Bid(current_bid)"""

    def _createLists(self):
        profile = self._profile.getProfile()
        domain = self._profile.getProfile().getDomain()
        all_bids = AllBidsList(domain)

        for bid in all_bids:
            self.utilBidMap[profile.getUtility(bid)] = bid
        self.listOfUtil = sorted(self.utilBidMap)

        clostest = self._take_closest(self.listOfUtil, decimal.Decimal(0.7))

    def _take_closest(self, myList, myNumber) -> decimal.Decimal:
        """
        Assumes myList is sorted. Returns closest value to myNumber.

        If two numbers are equally close, return the smallest number.
        """
        pos = bisect_left(myList, myNumber)
        if pos == 0:
            return myList[0]
        if pos == len(myList):
            return myList[-1]
        before = myList[pos - 1]
        after = myList[pos]
        if after - myNumber < myNumber - before:
            return after
        else:
            return before
