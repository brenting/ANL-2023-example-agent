import copy
import logging
import time
from random import randint, choice
from typing import cast, Dict

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue import Value
from geniusweb.issuevalue.Bid import Bid
from geniusweb.opponentmodel.FrequencyOpponentModel import FrequencyOpponentModel
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace import LinearAdditiveUtilitySpace
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter


class Agent61(DefaultParty):
    """
    Template agent that offers random bids until a bid with sufficient utility is offered.
    """

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile = None
        self._received_bids = list()
        self._sent_bids = list()
        self._best_bid = None
        self._last_received_bid: Bid = None
        self._last_sent_bid: Bid = None
        self._opponent_model: FrequencyOpponentModel = None
        self._reservation_value = None

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
            if isinstance(action, Offer) and self._me.getName() != action.getActor().getName():
                self._last_received_bid = cast(Offer, action).getBid()

                # Add the action to the opponent model, create one if it doesn't exist
                if self._opponent_model is None:
                    self._opponent_model = FrequencyOpponentModel.create()
                    self._opponent_model = self._opponent_model \
                        .With(newDomain=(self._profile.getProfile()).getDomain(), newResBid=None)
                    self._opponent_model = FrequencyOpponentModel.WithAction(self._opponent_model, action,
                                                                             self._progress)
                else:
                    self._opponent_model = FrequencyOpponentModel.WithAction(self._opponent_model, action,
                                                                             self._progress)

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
        return "Agent61"
    
    # Creates the ideal bid for the agent
    def _createBestBid(self):
        own_prof = self._profile.getProfile()

        bidVals: dict[str, Value] = dict()
        prof_vals = own_prof.getDomain().getIssuesValues()

        for issue in prof_vals.keys():
            utilvals = own_prof.getUtilities()[issue]
            bidVals[issue] = max(utilvals.getUtilities(), key=utilvals.getUtilities().get)

        self._best_bid = Bid(bidVals)

    # execute a turn
    def _myTurn(self):

        if self._best_bid is None:
            self._createBestBid()
        
        # If a reservation bid exists, its utility is the lower bound for accepting / sending offers
        if self._reservation_value is None:
            if self._profile.getProfile().getReservationBid() is None:
                self._reservation_value = 0
            else:
                self._reservation_value = self._profile.getProfile().getUtility(self._profile.getProfile().getReservationBid())

        # check if the last received offer if the opponent is good enough
        if self._isGood(self._last_received_bid):
            # if so, accept the offer
            action = Accept(self._me, self._last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            # bid = self._findBid()
            bid = self._findCounterBid()
            action = Offer(self._me, bid)

        # send the action
        return action

    # method that checks if we would agree with an offer
    def _isGood(self, bid: Bid) -> bool:
        if bid is None:
            return False
        profile = self._profile.getProfile()
        progress = self._progress.get(time.time() * 1000)

        diff = (self._opponent_model.getUtility(bid) - profile.getUtility(bid))
        
        # Ensure that bid is above reservation value. Additionally, in the early-mid game,
        # the utility should be above a time-dependent threshold. After that, the difference
        # in utilities between the agent and the opponent should be lower that 0.1
        return (profile.getUtility(bid) > self._reservation_value) and \
            (profile.getUtility(bid) > (0.9 - 0.1 * progress) or \
            (progress > 0.8 and diff < 0.1))
    
    # Defines the bidding strategy of the agent, returing the ideal
    # bid at the beginning, and otherwise generating intelligent counter-bids.
    # The method also saves sent bids for future bidding.
    def _findCounterBid(self) -> Bid:
        
        if self._progress.get(time.time() * 1000) < 0.1:
            selected_bid = self._best_bid
        else:
            selected_bid = self._findCounterBidMutate()

        self._last_sent_bid = selected_bid
        self._sent_bids.append(copy.deepcopy(selected_bid))
        return selected_bid
    
    # Creates a bid by mutating the agent's ideal bid to fit closer
    # to what the opponent model believes is beneficial to the other
    # party. The more time has passed, the more the ideal bid is mutated
    def _mutateBid(self, bid: Bid) -> Bid:

        own_prof = self._profile.getProfile()
        bw = own_prof.getWeights()

        sorted_weights = sorted(bw, key=bw.get)
        issues_vals = copy.deepcopy(bid.getIssueValues())
        current_index = int((len(sorted_weights) - 1.0) * self._progress.get(time.time() * 1000))

        while current_index >= 0 and own_prof.getUtility(Bid(issues_vals)) > self._reservation_value:
            sel_issue_vals = own_prof.getDomain().getIssuesValues()[sorted_weights[current_index]]
            issues_vals[sorted_weights[current_index]] = sel_issue_vals.get(randint(0, sel_issue_vals.size() - 1))
            current_index = current_index - 1

        return Bid(issues_vals)
   
    # Finds an intelligent counter bid, relying on opponent modelling and the
    # mutateBid function to find a bid that maximizes the Nash product, tries
    # to equalize both parties' utility value and that is above reservation
    def _findCounterBidMutate(self) -> Bid:

        own_prof = self._profile.getProfile()

        selected_bid = copy.deepcopy(self._last_sent_bid)
        max_nash_prod = (own_prof.getUtility(selected_bid) * self._opponent_model.getUtility(selected_bid))

        for _ in range(50):
            newbid = self._mutateBid(copy.deepcopy(self._best_bid))
            new_nash_prod = (own_prof.getUtility(newbid) * self._opponent_model.getUtility(newbid))

            diff = (self._opponent_model.getUtility(newbid) - own_prof.getUtility(newbid))

            if new_nash_prod > max_nash_prod and diff < 0.1 and own_prof.getUtility(newbid) > self._reservation_value:
                # print("OLD: " + str(max_nash_prod) + ", NEW: " + str(new_nash_prod))

                max_nash_prod = new_nash_prod
                selected_bid = copy.deepcopy(newbid)

        if self._progress.get(time.time() * 1000) > 0.95:
            for bid in self._sent_bids:
                if abs(self._opponent_model.getUtility(bid) - own_prof.getUtility(bid)) < 0.1 and \
                        self._opponent_model.getUtility(bid) > self._opponent_model.getUtility(selected_bid) and \
                        own_prof.getUtility(bid) > self._reservation_value:
                    selected_bid = bid

        return selected_bid
