import logging
import time
import numpy as np
from decimal import Decimal
from typing import cast, Dict

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.bidspace.BidsWithUtility import BidsWithUtility
from geniusweb.bidspace.Interval import Interval
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter

"""Author:
    Aleksander Buszydlik
    Karol Dobiczek
    Eva Noritsyna
    Andra Sav
"""


class Agent3(DefaultParty):
    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        # Last bid sent by this agent
        self._my_last_bid: Bid = None
        # Last bid received from the opponent
        self._last_received_bid: Bid = None
        # Utility of the last bid received from the opponent
        self._last_received_utility = -1
        # Bid received from the opponent two rounds ago (short term memory)
        self._previous_to_last_bid: Bid = None
        # Current statistics of opponent bids
        self._stat_dict = None
        # Statistics of opponent bids before this round
        self._last_stat_dict = None
        # Bids which should be taken into consideration
        self._possible_bids = None
        # Index of the current bid in the stored list of bids
        self._last_index = 0
        # Prediction for opponent's weights of issues
        self._opponent_weights = None
        # Prediction for opponent's preferences for issue values
        self._opponent_value_weights = None
        self._sorted_issue_values = dict()
        # Previous to last bid
        self._last_bid_to_process = None
        # Best welfare of opponent's bid seen so far
        self._best_bid_welfare = -1
        # Best utility of opponent's bid seen so far
        self._best_bid_utility = -1
        # Best bid seen so far
        self._best_received_bid: Bid = None
        # Progress when the bids were reranked last time
        self._last_calculation_progress = 0
        # Willingness to make big concessions (rerank bids)
        self._big_concessions_index = 0
        # Willingness to make small concessions
        self._small_concessions_index = 0

        # With small probability be the first to make a concession
        self._random_concessions_coefficient = 0.015
        # Steers the length of time when bids are not accepted
        self._exploration_coefficient = 0.9
        # Steers the length of time when bids are not reranked
        self._progress_coefficient = 0.1
        # Steers willingness to prioritize welfare over own utility
        self._selfishness_coefficient = 0.8

    def notifyChange(self, info: Inform):
        """This is the entry point of all interaction with your agent after is has been initialised.
        Args:
            info (Inform): Contains either a request for action or information.
        """

        # Settings message is the first message that will be send to the
        # agent containing all the information about the negotiation session.
        if isinstance(info, Settings):
            self._settings: Settings = cast(Settings, info)
            self._me = self._settings.getID()

            # Progress towards the deadline has to be tracked manually through the use of the Progress object
            self._progress: ProgressRounds = self._settings.getProgress()

            # Profile contains the preferences of the agent over the domain
            self._profile = ProfileConnectionFactory.create(
                info.getProfile().getURI(), self.getReporter()
            )

            # Store reservation utility if it exists
            profile = self._profile.getProfile()
            if profile.getReservationBid():
                self._reservation_utility = profile.getUtility(profile.getReservationBid())
            else:
                self._reservation_utility = 0

            # Prepare data structures for recording opponent bids
            self._stat_dict = self._prepare_stat_dict()
            self._last_stat_dict = self._stat_dict

            self._prepare_bid_data()
            self._create_possible_bids()

        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()
            actor = action.getActor()

            # Ignore action if it is our action
            if actor != self._me:
                # If it is an offer, set the last received bid
                if isinstance(action, Offer):
                    self._last_received_bid = cast(Offer, action).getBid()

        # Execute the move
        elif isinstance(info, YourTurn):
            action = self._myTurn()
            if isinstance(self._progress, ProgressRounds):
                self._progress = self._progress.advance()
            self.getConnection().send(action)

        # Finish the negotiation on agreement or deadline
        elif isinstance(info, Finished):
            self.terminate()

        else:
            self.getReporter().log(logging.WARNING, "Ignoring unknown info " + str(info))

    # Lets the geniusweb system know what settings this agent can handle
    def getCapabilities(self) -> Capabilities:
        return Capabilities(
            {"SAOP"},
            {"geniusweb.profile.utilityspace.LinearAdditive"}
        )

    # Terminates the agent and its connections
    # leave it as it is for this competition
    def terminate(self):
        self.getReporter().log(logging.INFO, "party is terminating:")
        super().terminate()
        if self._profile is not None:
            self._profile.close()
            self._profile = None

    

    def getDescription(self) -> str:
        return """Agent which employs frequency modelling to optimize for welfare of bids.
        At first bids are returned based on highest individual utility, then based on welfare.
        It concedes after the opponent concedes enough times or on its own with small probability.
        Acceptance is based on long exploration and then at the end choosing a bid that is at least
        as good as what has been previously seen. Always agrees in the last round."""

    # Execute a turn
    def _myTurn(self):
        self._collect_opponent_bid_data()

        # Check if the last received offer if the opponent is good enough
        if self._isGood(self._last_received_bid):
            # If so, accept the offer
            action = Accept(self._me, self._last_received_bid)

        # If not, find a bid to propose as counter offer
        else:
            bid = self._findBid()
            self._my_last_bid = bid
            action = Offer(self._me, bid)

        # Send the action
        return action

    # method that checks if we would agree with an offer
    def _isGood(self, bid: Bid) -> bool:
        """Evaluates the opponent's bid based on its utility and welfare.

        Args:
            bid: Set of values for every issue suggested by the opponent.

        Returns:
            bool: Confirmation whether the current bid is acceptable.
        """

        # If no bid was received then it is definitely bad
        if bid is None:
            return False

        # If we have never stored a bid previously, store it
        if self._best_received_bid is None:
            self._best_received_bid = bid

        profile = self._profile.getProfile()
        progress = self._progress.get(time.time() * 1000)

        # Find our utility for the opponent's bid
        current_utility = profile.getUtility(bid)
        # Find welfare for the opponent's bid
        new_bid_welfare = self._calculate_welfare(bid)
        # Welfare of the best stored bid may change in time so we have to recalculate it
        self._best_bid_welfare = self._calculate_welfare(self._best_received_bid)

        # Small concession index corresponds to the willingness to take the next best bet
        # Big concession index corresponds to the willingness to rerank bets
        if 0 < self._last_received_utility < current_utility:
            self._big_concessions_index += 1
            self._small_concessions_index += 1

        # Always store the best bid seen from the opponent
        if new_bid_welfare >= self._best_bid_welfare:
            self._best_received_bid = bid
            self._best_bid_welfare = new_bid_welfare

        # Also update the best bid utility if applicable
        if current_utility > self._best_bid_utility:
            self._best_bid_utility = current_utility

        self._last_received_utility = current_utility

        # Spend 90% of time looking for the best option your opponent can send
        if progress <= self._exploration_coefficient:
            return False

        # If it is the end of negotiation and we're at least meeting the reservation utility, concede.
        # It is always better to have an agreement than not.
        if progress >= 0.99 and current_utility > self._reservation_utility:
            return True

        # Accept a bid if it is at least as good as the best bid seen so far
        # and has a utility higher than our reservation value.
        if new_bid_welfare >= self._best_bid_welfare \
                and current_utility >= self._reservation_utility:
            return True

        # If none of the conditions hold, it is not a good bid.
        return False

    def _findBid(self) -> Bid:
        """Searches for a bid that can be suggested to the opponent.
        This uses a model of the opponent that is being created online.

        Returns:
            Bid: Set of values for every issue.
        """

        # If the negotiation is finishing resend the best received bid if it at least
        # fulfills reservation utility expectation
        if self._progress.get(time.time() * 1000) >= 0.99 and self._best_bid_utility >= self._reservation_utility:
            return self._best_received_bid

        # If it is time to run the welfare calculation the order of bids will change.
        # As we learn more about the opponent's bids, we can model their behaviour better.
        if self._run_welfare_calculation() and self._big_concessions_index >= 20:
            self._rerank_bids()
            self._big_concessions_index = 0
            self._last_index = 0

        # Choose the next bid from our list of available bids
        num_bids = len(self._possible_bids)
        bid = self._possible_bids[max(0, min(self._last_index, num_bids - 1))][0]

        if self._small_concessions_index == 1 \
                or np.random.rand() < self._random_concessions_coefficient:
            self._small_concessions_index = 0
            self._last_index += 1

        return bid

    def _run_welfare_calculation(self, step=0.1) -> bool:
        """Used to assess based on the progress of the negotiation whether the available bids
        should be reranked with the current prediction of social welfare.

        Args:
            step (float, optional): Informs how often the reranking should happen, defaults to 0.1.

        Returns:
            bool: True if a new ordering of bids should be generated.
        """
        current = (np.floor(self._progress.get(time.time() * 1000) / step)) * step
        result = current != self._last_calculation_progress
        self._last_calculation_progress = current

        return result and self._progress_coefficient < self._progress.get(time.time() * 1000)

    def _prepare_stat_dict(self) -> Dict:
        """Before the negotiation starts, generate a dictionary storing the frequency
        of opponent's bids for every value of every issue.

        Returns:
            Dict: Statistics of the opponent's bids initialized to 0
        """
        stats = dict()
        domain = self._profile.getProfile().getDomain()

        # Create a dictionary for every issue in the domain
        for issue in domain.getIssues():
            stats[issue] = dict()
            # Create a key for every possible value of this issue
            for value in domain.getValues(issue):
                stats[issue][value] = 0

        return stats

    def _prepare_bid_data(self):
        """Before the negotiation starts, generate dictionaries storing the opponent's
        decisions and the model of their utility function
        """
        utilities = self._profile.getProfile().getUtilities()
        self._last_bid_to_process = dict()
        self._opponent_weights = dict()  # Predictions for the weights of every issue
        self._opponent_value_weights = dict()  # Predictions for the weights of every value

        for utility in utilities:
            self._opponent_value_weights[utility] = np.zeros(len(self._stat_dict[utility]))
            self._opponent_weights[utility] = 1 / len(utilities)  # At the beginning all weights are equal
            self._last_bid_to_process[utility] = 0

    def _collect_opponent_bid_data(self):
        """Process the opponent's bid to update our model.
        Works based on the heuristics that if an opponent sends the same value for an issue frequently,
        then it is most likely very important for that opponent.
        Also, if an opponent changes their mind about an issue frequently,
        then the issue probably doesn't matter for the opponent too much.
        """
        self._last_stat_dict = self._stat_dict
        last_bid = self._last_received_bid
        if last_bid is None:
            return
        bid_data = last_bid.getIssueValues()
        alpha = 0.03  # Serves as the "learning rate" for the issue weigths

        for i, issue in enumerate(bid_data):
            # Record the use of certain value
            self._stat_dict[issue][bid_data[issue]] += 1

            if bid_data[issue] == self._last_bid_to_process[issue]:
                # Logarithm is used as some issues have less values than others which often makes
                # opponents unwilling to change even if the issue weight is relatively low.
                self._opponent_weights[issue] += alpha * np.log(len(self._stat_dict[issue])) * 0.3

            # Overwrite last used value
            self._last_bid_to_process[issue] = bid_data[issue]
            self._opponent_value_weights[issue] = calculate_weights(self._stat_dict[issue].copy(), method="normalize")

        weights = list(self._opponent_weights.values())
        weights = weights / np.sum(weights)
        for i, key in enumerate(self._opponent_weights):
            self._opponent_weights[key] = weights[i]

    def _create_possible_bids(self):
        """Generates a list of bids that may be acceptable for this agent.
        They are sorted based on decreasing utility first, and later based on welfare.
        """

        bids = BidsWithUtility.create(cast(LinearAdditive, self._profile.getProfile()))
        range = bids.getRange()

        domain_spread = range.getMax() - range.getMin()
        domain = self._profile.getProfile().getDomain()
        all_bids = AllBidsList(domain)
        domain_size = all_bids.size()
        possible_bids = []

        # On small domains just save all bids
        if domain_size <= 50000:
            interval = Interval(Decimal(self._reservation_utility), Decimal(1.0))
            for bid in bids.getBids(interval):
                # Calculate bid utility
                utility = self._profile.getProfile().getUtility(bid)
                # Save along with bid and the opponent's utility (to be calculated later)
                possible_bids.append([bid, utility, 0])

            # Sort by utility in descending order
            possible_bids.sort(key=lambda x: x[1], reverse=True)
            self._possible_bids = possible_bids
            return

        # On large domains we need to limit the number of bids taken into consideration
        else:
            max_bid = bids.getExtremeBid(isMax=True)
            # Strong assumption: utilities are uniformly distributed in range of domain
            # Take
            min_utility = range.getMax() - (domain_spread * 50000) / domain_size
            interval = Interval(Decimal(min_utility), range.getMax())
            for bid in bids.getBids(interval):
                bid_utility = self._profile.getProfile().getUtility(bid)
                if bid != max_bid and bid_utility > self._reservation_utility:
                    possible_bids.append([bid, bid_utility, 0])

            count = 0
            while count <= 40000:
                bid = all_bids.get(np.random.randint(0, domain_size - 1))
                if self._profile.getProfile().getUtility(bid) > self._reservation_utility:
                    possible_bids.append([bid, self._profile.getProfile().getUtility(bid), 0])
                count += 1

            # We always want at least one bid
            possible_bids.append([max_bid, self._profile.getProfile().getUtility(max_bid), 0])
            # Sort by utility in descending order
            possible_bids.sort(key=lambda x: x[1], reverse=True)
            self._possible_bids = possible_bids

    def _rerank_bids(self):
        """Sort the list of all acceptable bids based on the current estimate of their welfare
        """
        self._possible_bids.sort(key=lambda x: self._calculate_welfare(x[0]), reverse=True)

    def _calculate_welfare(self, bid, method="weighted_sum") -> Decimal:
        """Calculate welfare which is understood as the sum of own and opponent's utilities.
        Selfishness_coefficient can be used to steer preference for optimizing own utility.
        This seems to give better results than optimizing for the minimal utility.

        Args:
            bid (Bid): Set of values for every issue. At different stages of the negotiation,
            the welfare of the same bid may differ (due to refined opponent model).

        Returns:
            Decimal: Prediction of the welfare of a bid
        """
        own_utility = self._profile.getProfile().getUtility(bid)
        opponent_utility = self._calculate_opponent_utility(bid)

        if method == "weighted_sum":
            return Decimal(self._selfishness_coefficient) * Decimal(own_utility) \
                   + Decimal(1 - self._selfishness_coefficient) * Decimal(opponent_utility)

        else:
            return min(Decimal(own_utility), Decimal(opponent_utility))

    def _calculate_opponent_utility(self, bid) -> float:
        """Calculate the utility of a bid for the opponent based on the available model

        Args:
            bid (Bid): Set of values for every issue. At different stages of the negotiation,
            the opponent's utility of the same bid may differ (due to refined opponent model).

        Returns:
            float: Prediction of the utility of a bid for the opponent
        """
        domain = self._profile.getProfile().getDomain()
        opponent_utility = 0
        for issue in domain.getIssues():
            opponent_utility += self._opponent_weights[issue] \
                                * self._opponent_value_weights[issue][bid.getValue(issue)]
        return opponent_utility


def calculate_weights(count_dict, method="linear") -> Dict:
    """Models the predicted weights of an opponent for each value of an issue

    Args:
        count_dict (Dict): Stores number of changes in opponent's bids per issue
        method (str, optional): Method used to calculate weights, defaults to "linear".

    Returns:
        Dict: modified dictionary with a model of opponent's weights
    """
    counts = list(count_dict.values())

    # Predict the weights in a linear manner based on available counts
    if method == "linear":
        max_pos = np.argmax(counts)
        max_dist = max(max_pos + 1, len(counts) - max_pos)
        step = 1

        if len(counts) > 2:
            step = 1 / (max_dist - 1)

        for i in range(len(counts)):
            counts[i] = step * (max_dist - abs(i - max_pos) - 1)

    # Predict the weights by normalizing counts
    elif method == "normalize":
        counts = counts / np.max(counts)

    for i, key in enumerate(count_dict):
        count_dict[key] = counts[i]
    return count_dict