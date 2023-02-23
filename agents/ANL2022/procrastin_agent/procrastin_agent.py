from decimal import Decimal
import logging
import json
from os import path
from random import randint
from re import A
from time import time
from typing import Optional, cast

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.bidspace.BidsWithUtility import BidsWithUtility
from geniusweb.bidspace.Interval import Interval
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.LinearAdditiveUtilitySpace import (
    LinearAdditiveUtilitySpace,
)
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressTime import ProgressTime
from geniusweb.references.Parameters import Parameters
from numpy import append
from tudelft_utilities_logging.ReportToLogger import ReportToLogger
from .utils import opponent_model

from .utils.opponent_model import OpponentModel
from .utils.time_estimator import TimeEstimator
from .utils.bid_chooser_2 import BidChooser
from .utils.strategy_model import StrategyModel

# Some testing flags
test_use_accept = True
class ProcrastinAgent(DefaultParty):
    """
    The Mild Bunch Team's Python geniusweb agent.
    """

    def __init__(self):
        super().__init__()
        self.logger: ReportToLogger = self.getReporter()

        self.domain: Domain = None
        self.parameters: Parameters = None
        self.profile: LinearAdditiveUtilitySpace = None
        self.progress: ProgressTime = None
        self.me: PartyId = None
        self.other: str = None
        self.settings: Settings = None
        self.storage_dir: str = None
        self.strategy_model = None

        self.last_received_bid: Bid = None
        self.opponent_best_bid: Bid = None
        self.opp_best_self_util: Bid = None
        self.opponent_concession_bid: Bid = None
        self.opp_concession_self_util: Bid = 0.0
        self.alpha: float = 0.5
        self.lowest_acceptable: float = 1.0
        self.opponent_model: OpponentModel = None
        self.bid_chooser: BidChooser = None
        self.opponent_data: dict = None
        self.time_estimator: TimeEstimator = TimeEstimator()
        self.bids_sent: int = 0
        self.bids_received: int = 0
        self.logger.log(logging.INFO, "party is initialized")

        self.test_bids_left = []

    def getCapabilities(self) -> Capabilities:
        """MUST BE IMPLEMENTED
        Method to indicate to the protocol what the capabilities of this agent are.
        Leave it as is for the ANL 2022 competition

        Returns:
            Capabilities: Capabilities representation class
        """
        return Capabilities(
            set(["SAOP"]),
            set(["geniusweb.profile.utilityspace.LinearAdditive"]),
        )

    def getDescription(self) -> str:
        """MUST BE IMPLEMENTED

        Returns:
            str: Agent description
        """
        return "The Mild Bunch's ProcrastinAgent for the ANL 2022 competition." \
        " This agent puts off concesssion till the end of the negotiation."
        " It's developers are also procrastinagents! The Procrastin-A-Team!"

    def send_action(self, action: Action):
        """Sends an action to the opponent(s)

        Args:
            action (Action): action of this agent
        """
        self.getConnection().send(action)

    def extract_name(self, party: PartyId) -> str:
        return str(party).rsplit("_", 1)[0]

    def current_time(self) -> float:
        return self.progress.get(time() * 1000)

    def notifyChange(self, data: Inform):
        """MUST BE IMPLEMENTED
        This is the entry point of all interaction with your agent after is has been initialised.
        How to handle the received data is based on its class type.

        Args:
            data (Inform): Contains either a request for action or information.
        """

        # a Settings message is the first message that will be send to your
        # agent containing all the information about the negotiation session.
        if isinstance(data, Settings):
            self.settings = cast(Settings, data)
            self.me = self.settings.getID()

            # progress towards the deadline has to be tracked manually through the use of the Progress object
            self.progress = self.settings.getProgress()

            self.parameters = self.settings.getParameters()
            self.storage_dir = self.parameters.get("storage_dir")

            # the profile contains the preferences of the agent over the domain
            profile_connection = ProfileConnectionFactory.create(
                data.getProfile().getURI(), self.getReporter()
            )
            self.profile = profile_connection.getProfile()
            self.domain = self.profile.getDomain()
            profile_connection.close()

        # ActionDone informs you of an action (an offer or an accept)
        # that is performed by one of the agents (including yourself).
        elif isinstance(data, ActionDone):
            action = cast(ActionDone, data).getAction()
            actor = action.getActor()

            # ignore action if it is our action
            if actor != self.me:
                if self.other is None:
                    # obtain the name of the opponent, cutting of the position ID.
                    self.other = self.extract_name(actor)
                    # now that the name of the opponent is known, we load our stored data about them
                    self.load_data()

                # process action done by opponent
                self.opponent_action(action)
        # YourTurn notifies you that it is your turn to act
        elif isinstance(data, YourTurn):
            # execute a turn
            self.my_turn()

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(data, Finished):
            finished = cast(Finished, data)
            self.save_data(finished)
            # terminate the agent MUST BE CALLED
            self.logger.log(logging.INFO, "party is terminating:")
            super().terminate()
        else:
            self.logger.log(logging.WARNING, "Ignoring unknown info " + str(data))

    def opponent_action(self, action: Action):
        """Process an action that was received from the opponent.

        Args:
            action (Action): action of opponent
        """
        if isinstance(action, Accept):
            # opponent accepted, no response necessary
            pass

        # if it is an offer, set the last received bid
        if isinstance(action, Offer):
            offer = cast(Offer, action)
            self.bids_received += 1
            self.process_opponent_offer(offer)

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        # log opponent time
        self.time_estimator.self_times_add(self.current_time())
        # check if the last received offer is good enough
        if self.choose_accept(self.last_received_bid):
            # if so, accept the offer
            action = Accept(self.me, self.last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            bid = self.choose_bid()
            action = Offer(self.me, bid)
            self.bids_sent += 1

        # log self time
        self.time_estimator.opp_times_add(self.current_time())
        # send the action
        self.send_action(action)

################################################################################################
###################################    Our Implementation    ###################################
################################################################################################

    def load_data(self):
        # load_data is called as soon as the opponent is known. 
        # In the very rare case where the opponent never makes an offer, load_data is never called.
        if not path.exists(f"{self.storage_dir}/{self.other}.json"):
            # First round
            new_data = {}
            new_data["count"] = 0
            new_data["self_accepts"] = 0
            new_data["did_accept"] = []
            new_data["opponent_accepts"] = 0
            new_data["no_accepts"] = 0
            new_data["beta_values"] = []
            new_data["time_factor"] = 1.0
            new_data["alphas"] = []
            new_data["alpha_achieved"] = []
            self.opponent_data = new_data
        else:
            # Not first round
            with open(f"{self.storage_dir}/{self.other}.json", "r") as f:
                self.opponent_data = json.load(f)
        self.time_estimator.update_time_factor(self.opponent_data["time_factor"])

    def choose_bid(self) -> Bid:
        if self.bids_sent <= 5: 
            # Action to take before we have a decent estimate at how many turns are left
            # Send best bid
            bid_dict = {}
            for issue, valueset in self.profile.getUtilities().items():
                bid_dict[issue] = max(self.domain.getValues(issue), key = lambda v: valueset.getUtility(v))
            best_bid = Bid(bid_dict)
            return best_bid
        
        offers_left = self.time_estimator.turns_left(self.current_time())
        self.test_bids_left.append(offers_left)
        return self.bid_chooser.choose_bid(offers_left, self.current_time())

    def process_opponent_offer(self, offer: Offer):
        """Process an offer that was received from the opponent.

        Args:
            offer (Offer): offer from opponent
        """
        # create opponent model if it was not yet initialised
        if self.opponent_model is None:
            self.opponent_model = OpponentModel(self.domain)
            self.bid_chooser = BidChooser(self.profile, self.opponent_model, 0.5) # TODO update lowest acceptable number

        bid = offer.getBid()

        # set bid as last received
        self.last_received_bid = bid
        # update opponent model with bid
        self.opponent_model.update(bid, self.current_time())

        #set opp_highest_bid to either the first or calculated highest (opp POV) opponent bid
        update_opponent_best = False
        if self.opponent_best_bid is None:
            update_opponent_best = True
        elif self.opponent_model.get_predicted_utility(bid)[0] > self.opponent_model.get_predicted_utility(self.opponent_best_bid)[0]:
            #update opp_best_bid if new opponent bid is better for them than previous best
            update_opponent_best = True
        if update_opponent_best:
            self.opponent_best_bid = bid
            self.opp_best_self_util = float(self.profile.getUtility(bid))
            if self.strategy_model is None:
                self.strategy_model = StrategyModel(self.opponent_data["alphas"], self.opponent_data["beta_values"], self.opponent_data["did_accept"])
                self.alpha = self.strategy_model.max_u(self.opp_best_self_util, 0.5, 1.0, mag = 3)
            self.lowest_acceptable = self.opp_best_self_util + self.alpha * (1.0 - self.opp_best_self_util)
            self.bid_chooser.update_lowest_acceptable(self.lowest_acceptable)
        
        #set opp_concession_bid to either the first or highest (self POV) opponent bid
        update_opponent_concession = False
        if self.opponent_concession_bid is None:
            update_opponent_concession = True
        elif float(self.profile.getUtility(bid)) > self.opp_concession_self_util:
            update_opponent_concession = True
        if update_opponent_concession:
            self.opponent_concession_bid = bid
            self.opp_concession_self_util = float(self.profile.getUtility(bid))

        # update bid_chooser
        self.bid_chooser.update_bid(bid)

    def choose_accept(self, bid: Bid) -> bool:
        if bid is None:
            return False

        # very basic approach that accepts if the offer is valued above a certain amount of opponent's highest utility, calculated
        # through formula t = b + alpha (1.0 - b)
        # only accepts during last 20 turns or last 1/1000 of the negotiation (or our best was offered)
        bid_util = float(self.profile.getUtility(bid))
        time = self.current_time()
        conditions = [
            bid_util >= max(self.lowest_acceptable, self.opp_concession_self_util),
            any([
                self.time_estimator.turns_left(time) < 20,
                time > 0.999,
                bid_util >= 1.0,
            ]),
            #test_use_accept, # Tests agent behaviour without accepting
        ]
        return all(conditions)

    def save_data(self, finished: Finished):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        agreements = list(finished.getAgreements().getAgreements().items())
        save = self.opponent_data
        save["count"] += 1
        save["test_bid_pool_size"] = len(self.bid_chooser.bid_pool)
        save["test_time_list_self"] = self.time_estimator.self_times
        #save["test_time_list_opp"] = self.time_estimator.opp_times_adj
        save["test_offers_left"] = self.test_bids_left
        save["self_diff"] = self.time_estimator.self_diff
        
        opp_stuff = {"weights": {}}
        total_weight = 0.0
        for issue in self.domain.getIssues():
            opp_stuff[issue] = {}
            total_weight += self.opponent_model.issue_estimators[issue].weight
            opp_stuff["weights"][issue] = self.opponent_model.issue_estimators[issue].weight
            for value in self.domain.getValues(issue):
                opp_stuff[issue][value.getValue()] = self.opponent_model.issue_estimators[issue].get_value_utility(value)
        for issue in self.domain.getIssues():
            opp_stuff["weights"][issue] = self.opponent_model.issue_estimators[issue].weight / total_weight
        save["opponent_model"] = opp_stuff

        beta = float((self.opp_concession_self_util-self.opp_best_self_util)/(1 - self.opp_best_self_util))
        
        save["beta_values"].append(beta)

        if not agreements:
            agreement_bid = None
            agreement_party = None
            save["time_factor"] = self.time_estimator.get_new_time_factor(self.test_bids_left, len(self.bid_chooser.bid_pool))
            save["did_accept"].append(False)
        else:
            agreement = agreements[0]
            agreement_bid = agreement[1]
            agreement_party = agreement[0]
            save["did_accept"].append(True)
        if agreement_party is None:
            # No agreement was made (or rarely they accepted our first bid)
            save["no_accepts"] += 1
        elif self.extract_name(agreement_party) == self.extract_name(self.me):
            # We sent the agreement
            save["self_accepts"] += 1
        elif (self.other is not None) and self.extract_name(agreement_party) == self.other:
            # They accepted
            save["opponent_accepts"] += 1
        else:
            # Only way I can imagine getting here is if we offered 
            # the first bid and the opponent accepted.
            save["other_accepts"] = save.get("other_accepts", 0) + 1
            pass
        
        if agreement_bid is None:
            alpha_achieved = 0.0
        else:
            alpha_achieved = (float(self.profile.getUtility(agreement_bid)) - self.opp_best_self_util) / (1.0 - self.opp_best_self_util)
        save["alphas"].append(self.alpha)
        save["alpha_achieved"].append(alpha_achieved)

        with open(f"{self.storage_dir}/{self.other}.json", "w") as f:
            json.dump(save, f)