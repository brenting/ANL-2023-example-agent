import decimal
import time
from random import randint
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
from geniusweb.opponentmodel.FrequencyOpponentModel import FrequencyOpponentModel
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter

reservation_progress = 0.995
search_numb = 2500


class Agent41(DefaultParty):
    """
    Template agent that offers random bids until a bid with sufficient utility is offered.
    """

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        # self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._last_received_bid: Bid = None
        self._best_past_bid: Bid = None
        self.opponentModel = FrequencyOpponentModel.create()


        #  maximal advantage that our opponent might have over us to accept the bid in the later phase
        self.util_adv_from_accept = decimal.Decimal(0.2)
        # maximal advantage that our opponent might have over us
        # to propose the bid in the later phase
        self.util_adv_from_offer = decimal.Decimal(0.1)
        # maximal advantage that our agent might have over the opponent
        # to propose the bid in the later phase (potential to be removed)
        self.util_adv_to_offer = decimal.Decimal(0.8)
        # progress point at which the intermediate strategy starts being applied
        self.progress_mid = 0.6
        # progress point at which the late strategy starts being applied
        self.progress_fast = 0.95
        # starting utility range for which the offers are considered
        self.utility_range = [decimal.Decimal(0.9),
                              decimal.Decimal(1.1)]
        # linear decrease factors in different stages of the negotiations
        self.slow_decrease = decimal.Decimal(0.0005)
        self.mid_decrease = decimal.Decimal(0.001)
        self.fast_decrease = decimal.Decimal(0.002)
        # initial reservation value under which bids are denied
        self.minimal_reservation_val = decimal.Decimal(0.6)

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

            domain = self._profile.getProfile().getDomain()
            self.opponentModel = self.opponentModel.With(newDomain=domain, newResBid=0)

        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()

            self.opponentModel = self.opponentModel.WithAction(action=action,
                                                               progress=self._progress)

            # if it is an offer, set the last received bid
            if isinstance(action, Offer):
                self._last_received_bid = cast(Offer, action).getBid()


        # YourTurn notifies you that it is your turn to act
        elif isinstance(info, YourTurn):
            action = self._my_turn()
            if isinstance(self._progress, ProgressRounds):
                self._progress = self._progress.advance()
            self.getConnection().send(action)

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(info, Finished):
            # terminate the agent MUST BE CALLED
            self.terminate()
        # else:
        # self.getReporter().log(
        #     logging.WARNING, "Ignoring unknown info " + str(info)
        # )

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
        # self.getReporter().log(logging.INFO, "party is terminating:")
        super().terminate()
        if self._profile is not None:
            self._profile.close()
            self._profile = None

    

    # give a description of your agent
    def getDescription(self) -> str:
        return "Agent orange for Collaborative AI course"

    def _my_turn(self):
        """
        Executes a turn.
        """
        # update the utility range
        self._update_range()

        # check if the last received offer if the opponent is good enough
        if self._is_good(self._last_received_bid):
            # if so, accept the offer
            action = Accept(self._me, self._last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            bid = self._find_bid()
            action = Offer(self._me, bid)

        # send the action
        return action

    # method that checks if we would agree with an offer
    def _is_good(self, bid: Bid) -> bool:
        """
        Checks if the received offer is good enough to be accepted.
        """
        if bid is None:
            return False

        profile = self._profile.getProfile()

        # Update the best past bid effectively making it a reservation bid
        if self._best_past_bid is None:
            self._best_past_bid = bid
        elif profile.getUtility(bid) > profile.getUtility(self._best_past_bid):
            self._best_past_bid = bid

        # get the utility of us and our opponent (frequency model)
        our_util = profile.getUtility(bid)
        opp_util = self.opponentModel.getUtility(bid)
        progress = self._progress.get(time.time() * 1000)

        # immediately return the offer it is below our lower utility threshold
        if our_util < self.utility_range[0]:
            return False
        # if the progress reached a certain point,
        # accept the ofer only if it is not overwhelmingly better than the opponents
        if progress > self.progress_mid:
            return our_util + self.util_adv_from_accept >= opp_util
        # if this progress has not been reached yet,
        # simply accept the offer if it is better than our utility
        return True

    def _find_bid(self) -> Bid:
        """
        Find the most suitable bid to offer given the current state of negotiations.
        """
        domain = self._profile.getProfile().getDomain()
        profile = self._profile.getProfile()

        # verify if the reservation bid should be used
        if self._verify_reservation_val():
            return self._best_past_bid

        # store the best bid found so far
        best_bid: Bid = self._best_past_bid
        # store the difference between the utility of the best bid
        # and the upper threshold of the range
        best_dist = decimal.Decimal(1.0)

        all_bids = AllBidsList(domain)
        # search through a number of random bids to find a suitable bid
        for _ in range(search_numb):
            # get the random bid and the utility of it
            bid = all_bids.get(randint(0, all_bids.size() - 1))
            our_util = profile.getUtility(bid)
            # verify if the bid is suitable to be offered to the opponent
            if self._verify_bid(bid):
                best_bid = bid
                break
            # If the best bid was not found, check if the current bid is closer to idea value
            curr_dist = abs(our_util - self.utility_range[1])
            if curr_dist < best_dist:
                best_bid = bid
                best_dist = curr_dist

        return best_bid

    def _update_range(self):
        """
        Update the acceptance range depending on the current progress of the negotiation.
        The further we are into the negotiation, the faster the utility range drops.
        """
        progress = self._progress.get(time.time() * 1000)
        if progress < self.progress_mid:
            self.utility_range[1] = self.utility_range[1] - self.slow_decrease
            self.utility_range[0] = self.utility_range[0] - self.slow_decrease
        elif progress > self.progress_fast:
            self.utility_range[1] = self.utility_range[1] - self.fast_decrease
            self.utility_range[0] = self.utility_range[0] - self.fast_decrease
        else:
            self.utility_range[1] = self.utility_range[1] - self.mid_decrease
            self.utility_range[0] = self.utility_range[0] - self.mid_decrease

    def _verify_reservation_val(self) -> bool:
        """
        Return the best bid received so far, if the time is almost up and the bid is good enough.
        The reservation value is equal to the best offer received from the opponent.
        It is sent if our utility coming from this offer exceeds 0.7
        or if the utility of the reservation bid exceeds our upper utility threshold.
        """
        if self._best_past_bid is not None:
            reservation_val = self._profile.getProfile().getUtility(
                self._best_past_bid)
            if self._progress.get(
                    0) >= reservation_progress and reservation_val >= self.minimal_reservation_val:
                return True
            if self._profile.getProfile().getUtility(self._best_past_bid) >= self.utility_range[1]:
                return True
        return False

    def _verify_bid(self, bid: Bid) -> bool:
        """
        Verifies if the bid that our agent came up with is good enough to be offered to another agent.
        """
        progress = self._progress.get(time.time() * 1000)
        profile = self._profile.getProfile()
        our_util = profile.getUtility(bid)

        # do not consider the bid if it is worse than our reservation bid
        if self._best_past_bid is not None and our_util < profile.getUtility(self._best_past_bid):
            return False
        # if a certain point in the negotiation has not been reached,
        # propose the bid if it falls into the accepted utility range
        if progress < self.progress_mid:
            return self.utility_range[0] < our_util < self.utility_range[1]

        # otherwise, in addition to considering the utility range, also consider the utility of our opponent, make sure
        # that the utility difference between us and the opponent is not too high
        opp_util = self.opponentModel.getUtility(bid)
        return our_util + self.util_adv_from_offer > opp_util > our_util - self.util_adv_to_offer \
               and self.utility_range[0] < our_util < self.utility_range[1]
