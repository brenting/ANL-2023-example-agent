import logging
import random
from time import time
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
from tudelft_utilities_logging.ReportToLogger import ReportToLogger

from .utils.opponent_model import OpponentModel

class Group16Agent(DefaultParty):
    """
    Template of a Python geniusweb agent.
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

        self.last_received_bid: Bid = None
        self.opponent_model: OpponentModel = None
        self.logger.log(logging.INFO, "party is initialized")
        self.received_bids = []
        self.sent_bids = []
        self.reservation_value = 0.3
        self.threshold = 0.95
        self.delta = 0.05

    def notifyChange(self, data: Inform):
        """
        This is the entry point of all interaction with your agent after is has been initialised.
        How to handle the received data is based on its class type.

        Args:
            info (Inform): Contains either a request for action or information.
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
                # obtain the name of the opponent, cutting of the position ID.
                self.other = str(actor).rsplit("_", 1)[0]

                # process action done by opponent
                self.opponent_action(action)
        # YourTurn notifies you that it is your turn to act
        elif isinstance(data, YourTurn):
            # execute a turn
            self.my_turn()

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(data, Finished):
            self.save_data()
            # terminate the agent MUST BE CALLED
            self.logger.log(logging.INFO, "party is terminating:")
            super().terminate()
        else:
            self.logger.log(logging.WARNING, "Ignoring unknown info " + str(data))

    def getCapabilities(self) -> Capabilities:
        """
        Method to indicate to the protocol what the capabilities of this agent are.
        Leave it as is for the ANL 2022 competition

        Returns:
            Capabilities: Capabilities representation class
        """
        return Capabilities(
            {"SAOP"},
            {"geniusweb.profile.utilityspace.LinearAdditive"},
        )

    def send_action(self, action: Action):
        """Sends an action to the opponent(s)

        Args:
            action (Action): action of this agent
        """
        self.getConnection().send(action)

    # give a description of your agent
    def getDescription(self) -> str:
        """
        Returns:
            str: Agent description
        """
        return "Tradeoff agent with time-dependent concession style."

    def opponent_action(self, action):
        """Process an action that was received from the opponent.

        Args:
            action (Action): action of opponent
        """
        # if it is an offer, set the last received bid
        if isinstance(action, Offer):
            # create opponent model if it was not yet initialised
            if self.opponent_model is None:
                self.opponent_model = OpponentModel(self.domain)

            bid = cast(Offer, action).getBid()

            # update opponent model with bid
            self.opponent_model.update(bid)
            self.received_bids.append(bid)
            # set bid as last received
            self.last_received_bid = bid

    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        # check if the last received offer is good enough
        if self.accept_condition(self.last_received_bid):
            # if so, accept the offer
            action = Accept(self.me, self.last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            bid = self.find_bid()
            self.sent_bids.append(bid)
            action = Offer(self.me, bid)

        # send the action
        self.send_action(action)

    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        data = "Data for learning (see README.md)"
        with open(f"{self.storage_dir}/data.md", "w") as f:
            f.write(data)

    ###########################################################################################
    ######################################## BOA model ########################################
    ###########################################################################################

    def accept_condition(self, bid: Bid) -> bool:
        """
        This method implements the accepting strategy for our agent. We follow a model that exists of different phases.
        We included the following phases:
            1. Strictly exploring   0s - 1s     During this phase we do not accept any offer. Since heuristics tell us
                                                that most agents will not offer their best bids in the beginning. This
                                                also allows for building a better opponent model and bidding strategy
                                                that do not suffer from a cold start problem.
            2. Regular              1s - 9s     During this phase we accept bids that have a higher utility than the
                                                one we were about to offer.
            3. Eager                9s - 9.5s   Time is running out, so this strategy will accept any bid that is higher
                                                or equal to highest previously received bid.
            4. Desperate            9.5s - 10s  This is the last phase, and now it is really time to accept, so this
                                                strategy will accept anything. If we do not accept any offer the utility
                                                would be 0, so it is always better to accept.

        @param bid: The last bid offered by the opponent.
        @return:    A boolean indicating whether to accept or decline this offer.
        """
        if bid is None:
            return False

        # Progress of the negotiation session between 0 and 1 (1 is deadline).
        progress = self.progress.get(time() * 1000)

        # PHASE 1: STRICTLY EXPLORING
        # Never accept any offer during the first second.
        if progress < 0.1:
            return False

        # PHASE 2: REGULAR
        # Calculate the utility of the current bid.
        utility = self.profile.getUtility(bid)

        # Determine the minimum acceptable utility based on the progress of the negotiation.
        min_utility = 1.0 - (progress / 3.0)

        # Exploratory TFT and Similarity-Based TFT
        # AC const(a)(b) = accept iff u(b) >= a
        if utility >= min_utility:
            return True

        # If the utility gap between the received offer, and the proposed offer is smaller than 0.02, then the offer
        # should be accepted in 50 percent of the cases.
        if min_utility - float(utility) <= 0.02:
            return random.uniform(0, 1) < 0.5

        # PHASE 3: EAGER
        best_offer = max([self.profile.getUtility(bid) for bid in self.received_bids])
        # # If the bid is at least as good as the avg offered so far, accept it.
        if progress >= 0.90 and self.profile.getUtility(bid) >= best_offer:
            return True

        # Desperate
        # Check if the time remaining is less than the ACtime(T) threshold.
        # ACtime(T) is the fail safe mechanism: an agent may decide its better to have any deal
        if progress >= 0.95 and utility >= self.reservation_value:
            return True

        if progress >= 0.98:
            return True
        # Other se, reject the bid.
        else:
            return False

    def find_bid(self) -> Bid:
        # stuck with the algorithm - make concession
        self.make_concession()

        # generate set of bids that maximise own utility
        sorted_bids = self.sort_bids()
        bids = self.generate_own_similar_bids(sorted_bids)

        # no opponent bid made so far -> we start negotiation
        if self.last_received_bid is None:
            if len(bids) > 0:
                return bids[0]
            else:
                return sorted_bids[0]

        # no bids found to maximise own utility
        if len(bids) == 0:
            return self.get_random_bid()

        # find bid that maximises opponent utility from our own selected bids
        best_bid = bids[0]
        max_util = 0
        for bid in bids :
            opponent_util = self.opponent_model.get_predicted_utility(bid)
            if opponent_util > max_util:
                best_bid = bid
                max_util = opponent_util

        return best_bid

    def score_bid(self, bid: Bid, alpha: float = 0.95, eps: float = 0.1) -> float:
        """Calculate heuristic score for a bid

        Args:
            bid (Bid): Bid to score
            alpha (float, optional): Trade-off factor between self interested and
                altruistic behaviour. Defaults to 0.95.
            eps (float, optional): Time pressure factor, balances between conceding
                and Boulware behaviour over time. Defaults to 0.1.

        Returns:
            float: score
        """
        progress = self.progress.get(time() * 1000)

        our_utility = float(self.profile.getUtility(bid))

        time_pressure = 1.0 - progress ** (1 / eps)
        score = alpha * time_pressure * our_utility

        if self.opponent_model is not None:
            opponent_utility = self.opponent_model.get_predicted_utility(bid)
            opponent_score = (1.0 - alpha * time_pressure) * opponent_utility
            score += opponent_score

        return score

    ###########################################################################################
    ######################### Functions used by the bidding strategy ##########################
    ###########################################################################################
    def make_concession(self):
        if len(self.sent_bids) > 1:
            sent_utility_1 = self.profile.getUtility(self.sent_bids[len(self.sent_bids) - 1])
            received_utility_1 = self.profile.getUtility(self.received_bids[len(self.received_bids) - 1])

            sent_utility_2 = self.profile.getUtility(self.sent_bids[len(self.sent_bids) - 2])
            received_utility_2 = self.profile.getUtility(self.received_bids[len(self.received_bids) - 2])

            if sent_utility_1 >= sent_utility_2 and received_utility_1 < received_utility_2:
                self.threshold -= 0.05

    def sort_bids(self):
        all_bids = AllBidsList(self.profile.getDomain())
        bids = []
        for b in all_bids:
            bid = {"bid": b, "utility": self.profile.getUtility(b)}
            bids.append(bid)
        return sorted(bids, key=lambda d: d['utility'], reverse=True)

    def generate_own_similar_bids(self, sorted_bids):
        "Gather more opportunities as time passes by"
        similar_bids = []
        n = 5
        i = 0
        for bid in sorted_bids:
            if (self.threshold + self.delta) > bid["utility"] > (self.threshold - self.delta):
                similar_bids.append(bid["bid"])
                i += 1
            if i == n:
                break
        return similar_bids

    def get_random_bid(self):
        all_bids = AllBidsList(self.profile.getDomain())
        return all_bids.get(random.randint(0, all_bids.size() - 1))