import logging
import time
from random import randint
from tokenize import Number
from typing import cast, Set
from decimal import Decimal
import math

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
from geniusweb.profile.utilityspace import ValueSetUtilities
from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter


class Agent50(DefaultParty):
    """
    Template agent that offers random bids until a bid with sufficient utility is offered.
    """

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._last_received_bid: Bid = None
        self._last_send_bid: Bid = None
        self._incoming_bids: list[(Bid, Decimal)] = []
        self._aspiration_level: Decimal = 1.0
        self._asp_c = 0
        self._ordered_issue_values: dict[str, list[str]] = {}
        self._ordered_issue_values_is_initialized = False

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

    

    # Description of the agent
    def getDescription(self) -> str:
        return "Agent50"

    # Turn handler for the trade-off agent
    def _myTurn(self):
        # On the first turn, initialize the ordered issue values
        if not self._ordered_issue_values_is_initialized:
            self.initializeIssueValues()

        # Compute the utility value of the incoming bid
        utility_value: Decimal = self._calculateUtilityValue(self._last_received_bid)

        # log the incoming bid
        self._incoming_bids.append((self._last_received_bid, utility_value))

        # Check for a deadlock (when the utility value of the incoming bid is lower than that of the previous incoming bid)
        # If so, decrease aspiration level (can be time-dependent) -> this is where the concession is made
        if (
                len(self._incoming_bids) > 1
                and utility_value < self._incoming_bids[-2][1]
        ):
            self._decreaseAspirationLevel()

        # Generate a bid at the current aspiration level and set it as the last sent bid
        next_bid: Bid = self._generateBid()
        self._last_send_bid = next_bid

        # If the incoming bid is good enough, accept (when the received offer is better than last proposed offer)
        if self._isAcceptable(self._last_received_bid):
            action = Accept(self._me, self._last_received_bid)
        else: # Else, offer the generated bid
            action = Offer(self._me, next_bid)

        return action

    # Get the fraction of unique incoming bids
    def _getFractionUniqueIncomingBids(self):
        unique_received_bids = set([x[0] for x in self._incoming_bids])
        return (
            len(unique_received_bids) / len(self._incoming_bids)
            if len(self._incoming_bids) >= 1
            else 1
        )

    # Decreases the aspiration level depending on fraction of unique incoming bids and progress
    def _decreaseAspirationLevel(self):
        fraction_progress = self._progress.get(time.time() * 1000)
        self._aspiration_level -= (
            0.002 * (self._getFractionUniqueIncomingBids() + 0.5)
        ) * (math.pow(fraction_progress, 2) + 1)

    # Calculates the utility value of the given bid
    def _calculateUtilityValue(self, bid: Bid) -> Decimal:
        if not bid:
            return 0
        return self._profile.getProfile().getUtility(bid)

    # Returns true iff the given bid is better than the last proposed bid and the reservation value (ACnext)
    def _isAcceptable(self, bid: Bid) -> bool:
        # Not acceptable if bid is None or there is no last send bid
        if not bid or not self._last_send_bid:
            return False

        # Calculate utility value of the bid
        uv = self._calculateUtilityValue(bid)

        reservation_bid = self._profile.getProfile().getReservationBid()
        # Check if utility value of bid is higher than last proposed bid and the reservation bid
        if not reservation_bid:
            return uv >= self._calculateUtilityValue(self._last_send_bid)
        else:
            return uv > self._calculateUtilityValue(
                reservation_bid
            ) and uv >= self._calculateUtilityValue(self._last_send_bid)

    # Compute the variability of given issue
    def _computeVariability(self, issue: str) -> Decimal:
        # No variability if there is only one bid
        if len(self._incoming_bids) < 2:
            return 0

        # Get the total of changes between successive bids
        changes = 0
        n = len(self._incoming_bids) - 1
        for i in range(n):
            if (
                not self._incoming_bids[n - 1]
                or not self._incoming_bids[n - 1][0]
                or not self._incoming_bids[n - (i + 1)]
                or not self._incoming_bids[n - (i + 1)][0]
            ):
                continue
            if self._incoming_bids[n - i][0].getValue(issue) != self._incoming_bids[
                n - (i + 1)
            ][0].getValue(issue):
                changes += 1

        # Variability is total changes divided by total bids
        return changes / n

    # Bid generator for the trade-off agent
    def _generateBid(self) -> Bid:
        # Calculate the variance of each issue in the bids of the opposing party
        variabilities = []
        for issue in self._profile.getProfile().getDomain().getIssues():
            variabilities.append((issue, self._computeVariability(issue)))

        # Order issues in the most recent incoming bid by variance, descending
        # (assumption: higher variance issues are less important for the opponent)
        variabilities.sort(key=lambda x: x[1], reverse=True)
        issues_sorted_by_variance = [v[0] for v in variabilities]
        bid_values = (
            self._last_received_bid.getIssueValues().copy()
            if self._last_received_bid
            else dict()
        )

        if len(bid_values) < len(variabilities):
            bid_values = dict()
            for issue in issues_sorted_by_variance:
                bid_values[issue] = list(self._ordered_issue_values[issue])[-1]

        new_proposed_bid = Bid(bid_values)

        # Raise the value of each issue incrementally until the aspiration level has been reached
        # Max out the first issue, if that does not reach the aspiration level, continue to the next issue
        for issue in issues_sorted_by_variance:
            ordered_values = list(self._ordered_issue_values[issue])
            current_value = bid_values[issue]
            index = ordered_values.index(current_value)
            while (index < len(ordered_values)) & (
                self._calculateUtilityValue(new_proposed_bid) < self._aspiration_level
            ):
                bid_values[issue] = ordered_values[index]
                new_proposed_bid = Bid(bid_values)
                index += 1

        # Decrease aspiration level if new proposed bid is the same as last proposed bid
        if self._last_send_bid and new_proposed_bid == self._last_send_bid:
            self._decreaseAspirationLevel()

        # Return the bid
        return new_proposed_bid

    # Initializes the data structure storing the issue values ordered by utility value (ascending)
    def initializeIssueValues(self):
        profile = self._profile.getProfile()

        utilities_per_value_per_issue: dict[
            str, ValueSetUtilities
        ] = profile.getUtilities()

        # Loop through all the issues in the domain
        domain = profile.getDomain().getIssuesValues()
        for issue in domain:
            # Get the issue and utility values for the current issue
            utility_values = utilities_per_value_per_issue[issue].getUtilities()
            # Sort the issue values by their utility values, ascending
            values_sorted_by_utility = dict(
                sorted(utility_values.items(), key=lambda item: item[1])
            )
            # Store the results
            self._ordered_issue_values[issue] = values_sorted_by_utility.keys()

        # Change the state variable to note that the data structure has been initialized
        self._ordered_issue_values_is_initialized = True
